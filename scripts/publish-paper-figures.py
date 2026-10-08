"""Copy current publication artifacts into the private workbench gallery."""
import hashlib
import json
from pathlib import Path
import shutil

root=Path(__file__).resolve().parents[1]
source=root/'output'/'publication'
target=root.parent/'tgap-sandbox'/'publication'
target.mkdir(exist_ok=True)
metadata=json.loads((source/'figure_metadata.json').read_text(encoding='utf-8'))
records={f['figure']:f for f in metadata['figures'] if '/' not in f['figure']}
captions={
 'fig0_tgap_architecture':('How TGAP works','Follow the original graph through concept changes, predictions and explanations.','Architecture illustration, not an experimental finding.'),
 'fig1_final_model_separated_impacts':('Concept impacts, separated by model','Each dot is a valid recorded test. Models and concept-unit groups keep their own panels.','Compare only within the permitted semantic group in one dataset/model panel; no global ranking.'),
 'fig3_bridge_matrix':('Connections between communities','A matrix counts cross-community connections; lines show their changes through time.','Controlled four-community synthetic demonstration; not a real-data finding.'),
 'fig4_local_graph':('One graph explanation','Compare the original graph, its changed version, and the edited connections.','One controlled synthetic local explanation; edge edits are not individual attribution scores.'),
 'fig5_temporal_local':('When a concept matters','Colors show the response to changing one time step at a time.','Synthetic demonstration. Present-only and trajectory models have distinct response patterns.'),
 'fig6_impact_distribution':('Exploratory spread of recorded impacts','Dots show the spread of recorded valid impacts across datasets.','Exploratory mixed-model plot with a signed-log axis. Model scales and concept units differ: do not use it for cross-model or cross-concept numerical ranking.'),
 'fig7_tgn_seed_stability':('Learned-model seed stability','Compare recorded learned-model results across training seeds.','Recorded TGN evaluation, not a learned model fitted by the web workbench.'),
 'fig8_dependence':('Structure and measured response','Compare node degree or edge persistence with the measured response to removal.','Node and edge occlusions are separate quantities. Association does not establish causation.'),
 'fig9_true_beeswarm':('Individual concept responses','Each dot is a recorded response; dots spread vertically to remain visible.','Read within one semantic row; model outputs and incompatible concepts are not pooled into a ranking.'),
 'fig10_publication_boxplot':('Response distributions by model','Boxes summarize the recorded spread of compatible concept responses.','Compare within a single model panel; Centralization and Bridge Trend are excluded.'),
 'fig11_local_bar':('One local element explanation','Bars show how one prediction changed when particular elements were removed.','A local element-occlusion explanation, not a ranking of TGAP concepts.'),
 'fig12_temporal_edge_time':('Connections and time','Cells show the measured response to removing one connection at one time step.','TGAP edge-time occlusion, not TSHAP. Values are not summed across time.'),
}
figures=[]
for image in sorted(source.glob('*.png')):
    if image.stem not in captions:
        raise ValueError('Add a reviewed caption before publishing '+image.name)
    title,description,scope=captions[image.stem]
    record=records.get(image.stem,{})
    formats=[]
    for suffix in ('png','pdf'):
        path=image.with_suffix('.'+suffix)
        if path.exists():
            shutil.copy2(path,target/path.name)
            formats.append(suffix)
    figures.append(dict(id=image.stem,title=title,description=description,scope=scope,formats=formats,
                        source='output/publication/'+image.name,
                        sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
                        metadata=record))
(target/'manifest.json').write_text(json.dumps(dict(schema_version=1,figures=figures),indent=2),encoding='utf-8')
print('Published',len(figures),'reviewed figures. Superseded figures were excluded.')
