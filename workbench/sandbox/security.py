"""Local CAPTCHA, persistent authentication throttles and hashed accounts."""
import base64
from collections import deque, OrderedDict
import hashlib
import hmac
import io
import secrets
import threading
import time

from fastapi import HTTPException
from PIL import Image, ImageDraw, ImageFont


def generate_answer():
    return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(6))


def captcha_png(answer):
    canvas=Image.new('RGB',(270,90),'#f0f5fa')
    draw=ImageDraw.Draw(canvas)
    for _ in range(8):
        draw.line([(secrets.randbelow(270),secrets.randbelow(90)),(secrets.randbelow(270),secrets.randbelow(90))],fill='#b0c3d6',width=2)
    try:font=ImageFont.truetype('arialbd.ttf',35)
    except OSError:
        try:font=ImageFont.truetype('DejaVuSans.ttf',35)
        except OSError:font=ImageFont.load_default(size=35)
    for i,char in enumerate(answer):
        tile=Image.new('RGBA',(45,60),(0,0,0,0))
        ImageDraw.Draw(tile).text((7,6),char,font=font,fill='#173d68')
        tile=tile.rotate(secrets.randbelow(19)-9,resample=Image.Resampling.BICUBIC)
        canvas.paste(tile,(12+i*40,12+secrets.randbelow(8)),tile)
    out=io.BytesIO();canvas.save(out,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()


def hash_password(password):
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
    return f'pbkdf2-sha256$600000${salt}${digest}'


def verify_password(password,encoded):
    try:
        algorithm,count,salt,expected=encoded.split('$')
        if algorithm!='pbkdf2-sha256' or int(count)!=600000:return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(count)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError):return False


class Security:
    def __init__(self,db,secret):
        self.db,self.secret=db,secret.encode()
        self.hash_slots=threading.BoundedSemaphore(4)
        self.lock=threading.Lock()
        self.peers=OrderedDict()
        self.global_requests=deque()
        self.active=0
        self.dummy=hash_password(secrets.token_urlsafe(32))
        with db() as conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS registered_accounts(
                username TEXT PRIMARY KEY COLLATE NOCASE, password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'participant' CHECK(role='participant'),
                created REAL NOT NULL, disabled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS captcha_challenges(
                id TEXT PRIMARY KEY,digest TEXT NOT NULL,binding TEXT NOT NULL,
                purpose TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_limits(
                bucket TEXT PRIMARY KEY,window REAL NOT NULL,count INTEGER NOT NULL);
            ''')

    def admit(self,peer):
        now=time.monotonic()
        with self.lock:
            while self.global_requests and self.global_requests[0]<now-1:self.global_requests.popleft()
            if len(self.global_requests)>=200 or self.active>=64:
                raise HTTPException(429,'The service is busy. Please wait a moment.',headers={'Retry-After':'5'})
            if peer not in self.peers:
                if len(self.peers)>=8192:
                    old,times=next(iter(self.peers.items()))
                    if times and times[-1]>now-60:
                        raise HTTPException(429,'The service is busy. Please wait.',headers={'Retry-After':'60'})
                    self.peers.pop(old)
                self.peers[peer]=deque()
            times=self.peers[peer]
            while times and times[0]<now-60:times.popleft()
            if len(times)>=600 or sum(t>now-1 for t in times)>=60:
                raise HTTPException(429,'Too many requests. Please wait.',headers={'Retry-After':'60'})
            times.append(now);self.peers.move_to_end(peer)
            self.global_requests.append(now);self.active+=1

    def release(self):
        with self.lock:self.active=max(0,self.active-1)

    def rate(self,bucket,limit,seconds):
        now=time.time();window=now-now%seconds
        key=hmac.new(self.secret,bucket.encode(),hashlib.sha256).hexdigest()
        with self.db() as conn:
            count=conn.execute('''INSERT INTO auth_limits VALUES (?,?,1)
              ON CONFLICT(bucket) DO UPDATE SET count=CASE WHEN auth_limits.window=excluded.window
              THEN auth_limits.count+1 ELSE 1 END,window=excluded.window RETURNING count''',(key,window)).fetchone()[0]
            if secrets.randbelow(50)==0:
                conn.execute('DELETE FROM auth_limits WHERE window<?',(now-172800,))
        if count>limit:
            raise HTTPException(429,'Too many attempts. Please try again later.',headers={'Retry-After':str(max(1,int(window+seconds-now)))})

    def binding(self,request):
        peer=request.client.host if request.client else 'unknown'
        cookie=request.cookies.get('tgap_challenge_session','')
        return hmac.new(self.secret,(peer+'|'+cookie).encode(),hashlib.sha256).hexdigest()

    def issue(self,request,response,purpose,secure=False):
        peer=request.client.host if request.client else 'unknown'
        self.rate('captcha:'+peer,30,60)
        self.rate('captcha:global',300,60)
        cookie=request.cookies.get('tgap_challenge_session')
        if not cookie:
            cookie=secrets.token_urlsafe(32)
            response.set_cookie('tgap_challenge_session',cookie,max_age=3600,httponly=True,samesite='strict',secure=secure)
        binding=hmac.new(self.secret,(peer+'|'+cookie).encode(),hashlib.sha256).hexdigest()
        answer=generate_answer();token=secrets.token_urlsafe(24)
        digest=hmac.new(self.secret,(token+'|'+answer).encode(),hashlib.sha256).hexdigest()
        now=time.time()
        with self.db() as conn:
            conn.execute('DELETE FROM captcha_challenges WHERE expires<?',(now,))
            if conn.execute('SELECT count(*) FROM captcha_challenges').fetchone()[0]>=5000:
                raise HTTPException(429,'Verification is busy. Please try again shortly.')
            conn.execute('DELETE FROM captcha_challenges WHERE binding=? AND purpose=?',(binding,purpose))
            conn.execute('INSERT INTO captcha_challenges VALUES (?,?,?,?,?)',(token,digest,binding,purpose,now+300))
        return dict(id=token,image=captcha_png(answer),expires_in=300)

    def check(self,request,token,answer,purpose):
        with self.db() as conn:
            row=conn.execute('DELETE FROM captcha_challenges WHERE id=? RETURNING *',(token,)).fetchone()
        supplied=hmac.new(self.secret,(token+'|'+answer.strip().upper()).encode(),hashlib.sha256).hexdigest()
        if not row or row['expires']<time.time() or row['purpose']!=purpose or not hmac.compare_digest(row['binding'],self.binding(request)) or not hmac.compare_digest(row['digest'],supplied):
            raise HTTPException(400,'Verification was incorrect or expired. Please try the new image.')

    def registered(self,username):
        with self.db() as conn:row=conn.execute('SELECT * FROM registered_accounts WHERE username=?',(username,)).fetchone()
        if not row or row['disabled']:return None
        return dict(username=row['username'],password_hash=row['password_hash'],role='participant',
                    signature=hmac.new(self.secret,(row['username']+'|'+row['password_hash']).encode(),hashlib.sha256).hexdigest())

    def password_slot(self):
        if not self.hash_slots.acquire(blocking=False):
            raise HTTPException(429,'Sign-in is busy. Please try again shortly.',headers={'Retry-After':'5'})

    def verify(self,password,account):
        self.password_slot()
        try:
            if account and 'password' in account:
                # Retain operator-managed file accounts; match constant-time and equalize KDF cost.
                verify_password(password,self.dummy)
                return hmac.compare_digest(hmac.digest(self.secret,password.encode(),'sha256'),hmac.digest(self.secret,account['password'].encode(),'sha256'))
            return verify_password(password,account['password_hash'] if account else self.dummy) and bool(account)
        finally:self.hash_slots.release()

    def register(self,username,password):
        self.password_slot()
        try:encoded=hash_password(password)
        finally:self.hash_slots.release()
        with self.db() as conn:
            conn.execute('INSERT INTO registered_accounts(username,password_hash,created) VALUES (?,?,?)',(username,encoded,time.time()))
