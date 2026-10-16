'use strict';
let authMode='login',authChallenge=null,authSequence=0;
async function refreshAuthCaptcha(){
  const sequence=++authSequence;authChallenge=null;$('sign-in').disabled=true;$('captcha-refresh').disabled=true;$('captcha-answer').value='';
  try{const challenge=await api('/captcha?purpose='+authMode);if(sequence!==authSequence)return;authChallenge=challenge;$('captcha-image').src=challenge.image;}
  catch(error){if(sequence===authSequence)$('login-error').textContent=error.message;}
  finally{if(sequence===authSequence){$('captcha-refresh').disabled=false;$('sign-in').disabled=!authChallenge;}}
}
function setAuthMode(mode){
  authMode=mode;const registration=mode==='register';
  $('auth-title').textContent=registration?'Create your account.':'Welcome to the lab.';
  $('auth-description').textContent=registration?'Choose a username and password to start your own experiments.':'Sign in to return to your experiments, or create your own account.';
  $('auth-login').setAttribute('aria-pressed',String(!registration));$('auth-register').setAttribute('aria-pressed',String(registration));
  $('username-help').hidden=!registration;$('password-help').hidden=!registration;$('confirm-password-field').hidden=!registration;
  $('confirm-password').disabled=!registration;$('confirm-password').required=registration;
  $('username').maxLength=registration?32:80;$('username').minLength=registration?3:1;
  $('password').minLength=registration?15:1;$('password').maxLength=registration?128:150;$('password').autocomplete=registration?'new-password':'current-password';
  $('sign-in').textContent=registration?'Create account & enter':'Sign in';$('login-error').textContent='';refreshAuthCaptcha();
}
$('auth-login').onclick=()=>setAuthMode('login');$('auth-register').onclick=()=>setAuthMode('register');$('captcha-refresh').onclick=refreshAuthCaptcha;
$('login-form').onsubmit=async event=>{
  event.preventDefault();$('login-error').textContent='';
  if(authMode==='register'&&$('password').value!==$('confirm-password').value){$('login-error').textContent='The passwords do not match.';return;}
  if(!authChallenge){$('login-error').textContent='Load a new verification image before continuing.';return;}
  $('sign-in').disabled=true;
  try{const user=await api(authMode==='register'?'/register':'/login',{method:'POST',body:JSON.stringify({username:$('username').value.trim(),password:$('password').value,captcha_id:authChallenge.id,captcha_answer:$('captcha-answer').value})});
    authChallenge=null;$('password').value='';$('confirm-password').value='';$('captcha-answer').value='';location.hash='guide';await openWorkspace(user);
  }catch(error){$('login-error').textContent=error.message;await refreshAuthCaptcha();}
  finally{$('sign-in').disabled=!authChallenge;}
};
if(!$('login').hidden)refreshAuthCaptcha();
