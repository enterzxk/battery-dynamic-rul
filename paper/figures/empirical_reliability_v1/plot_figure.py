from pathlib import Path
import sys,json,csv,hashlib
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator,FuncFormatter,NullLocator
D=Path(__file__).resolve().parent;R=Path('/home/yndx/zxk/rul')
sys.path.insert(0,str(D/'_qa'))
from audit_panel_alignment import require_matplotlib_panel_alignment
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
p=json.loads((D/'figure_contract.json').read_text())
for rel,h in p['source_sha256'].items():assert sha(R/rel)==h
rows=list(csv.DictReader((R/p['prediction_source']).open()))
pc=json.loads((R/p['mixture_cell_metrics']).read_text())
lp=json.loads((R/p['linear_cell_metrics']).read_text())
ids=sorted({r['cell_id'] for r in rows});assert len(ids)==10 and len(rows)==4567
colors={'linear':'#909090','early':'#4777A3','dynamic':'#D68B4B','mixture':'#6D5F9E','truth':'#181818'}
styles={'linear':':','early':'--','dynamic':'-','mixture':'-.','truth':'-'}
marks={'linear':'s','early':'^','dynamic':'o','mixture':'D'}
labels={'linear':'Linear (no fit)','early':'Early survival','dynamic':'Dynamic','mixture':'Equal CDF','truth':'Observed RUL'}
arms=['linear','early','dynamic','mixture'];old={'early':'early_survival','dynamic':'dynamic','mixture':'fixed_half_CDF_mixture'}
metric=[];trajectories=[]
for cid in ids:
 linear=next(r for r in lp if r['cell_id']==cid)
 for arm in arms:
  a=linear['full_linear'] if arm=='linear' else next(r for r in pc if r['cell_id']==cid and r['arm']==old[arm])
  metric.append(dict(cell_id=cid,arm=arm,origins=linear['all_origins'],MAE=a['MAE'],severe_over100=a['severe_over100'],coverage80='' if arm=='linear' else a['coverage80']))
with (D/'source_cell_metrics.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(metric[0]));w.writeheader();w.writerows(metric)
mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],'font.size':7,'axes.labelsize':7,'axes.titlesize':7.2,'xtick.labelsize':6.5,'ytick.labelsize':6.5,'legend.fontsize':6.5,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7,'xtick.major.width':.7,'ytick.major.width':.7,'svg.fonttype':'none','pdf.fonttype':42,'svg.hashsalt':'rul-empirical-v1','path.simplify':False,'savefig.facecolor':'white'})
width_mm,height_mm=180,140
fig,axes=plt.subplots(2,2,figsize=(width_mm/25.4,height_mm/25.4),gridspec_kw={'left':.105,'right':.98,'bottom':.115,'top':.84,'wspace':.34,'hspace':.64})
a,b,c,d=axes.ravel()
def log_axis(ax,ticks,lim):
 ax.set_yscale('log');ax.set_ylim(*lim);ax.yaxis.set_major_locator(FixedLocator(ticks));ax.yaxis.set_minor_locator(NullLocator());ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:format(v,'g')))
for cid in ids:
 vals=[next(x['MAE'] for x in metric if x['cell_id']==cid and x['arm']==arm) for arm in arms]
 assert all(v>0 for v in vals)
 a.plot(range(4),vals,color='#C8C8C8',linewidth=.6,zorder=1)
 for j,arm in enumerate(arms):a.plot(j,vals[j],marker=marks[arm],markersize=3.4,color=colors[arm],linestyle='none',zorder=2)
log_axis(a,[1,10,100,1000,10000],(3,5000))
a.set_xticks(range(4));a.set_xticklabels(['Linear','Early','Dynamic','Equal CDF'])
a.set_ylabel('Per-cell MAE (cycles; log scale)');a.set_xlim(-.3,3.3)
a.set_title('Paired errors across 10 source cells',loc='left',pad=8)
for j,cid in enumerate(ids):
 for offset,arm in zip([-.18,0,.18],['early','dynamic','mixture']):
  z=next(x for x in metric if x['cell_id']==cid and x['arm']==arm);b.plot(j+offset,100*z['coverage80'],marker=marks[arm],markersize=3.4,color=colors[arm],linestyle='none')
b.axhline(80,color='#555555',linestyle=':',linewidth=.8,zorder=0)
b.set_ylim(-5,105);b.set_yticks([0,20,40,60,80,100]);b.set_xlim(-.6,9.6)
b.set_xticks(range(10));b.set_xticklabels([cid.replace('MATR_','') for cid in ids],rotation=45,ha='right',rotation_mode='anchor')
b.set_ylabel('80% interval coverage (%)');b.set_title('Mean coverage conceals cell failures',loc='left',pad=8)
coverage_rows=30
for ax,cid in [(c,'MATR_b2c1'),(d,'MATR_b4c7')]:
 z=sorted([r for r in rows if r['cell_id']==cid],key=lambda r:int(r['origin']));x=np.array([int(r['origin']) for r in z]);assert np.all(np.diff(x)==1)
 for arm,col in [('linear','linear_RUL'),('early','early_RUL'),('dynamic','dynamic_RUL'),('mixture','mixture_RUL'),('truth','true_RUL')]:
  y=np.array([float(r[col]) for r in z]);assert np.isfinite(y).all() and np.all(y>0)
  ax.plot(x,y,color=colors[arm],linestyle=styles[arm],linewidth=1.15 if arm in ['truth','mixture'] else .95,label=labels[arm])
 ax.set_xlim(x.min(),x.max());ax.set_xlabel('Observation cycle');ax.set_ylabel('RUL (cycles; log scale)')
 ax.set_title(('b2c1: linear baseline exception' if cid.endswith('b2c1') else 'b4c7: overestimation persists'),loc='left',pad=8)
 log_axis(ax,[.1,1,10,100] if ax is c else [1,10,100,1000,10000],(.1,100) if ax is c else (.5,40000))
 for line in ax.lines:
  low,high=ax.get_ylim();assert np.min(line.get_ydata())>=low and np.max(line.get_ydata())<=high
 for r in z:trajectories.append({k:r[k] for k in ['cell_id','origin','true_RUL','linear_RUL','early_RUL','dynamic_RUL','mixture_RUL']})
c.set_xticks([100,120,140]);d.set_xticks([100,200,300,400,500])
for label,ax in zip('abcd',axes.ravel()):
 ax.annotate(label,xy=(0,1),xycoords='axes fraction',xytext=(-22,8),textcoords='offset points',fontsize=8,fontweight='bold',ha='left',va='baseline')
 ax.tick_params(direction='out',length=2.5,pad=2.3)
handles=[Line2D([],[],color=colors[k],linestyle=styles[k],linewidth=1.15,label=labels[k]) for k in arms+['truth']]
fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.54,.945),ncol=5,frameon=False,columnspacing=1.2,handlelength=2.4)
fig.text(.105,.965,'Average gains do not establish individual reliability',fontsize=8.2,ha='left',va='top')
fig.text(.105,.035,'10 exposed development source cells; fixed seed 42. Descriptive evidence, not independent confirmation.',fontsize=6.2,ha='left')
fig.canvas.draw()
alignment=require_matplotlib_panel_alignment(fig,json_out=D/'figure.alignment.json',overlay_svg=D/'figure.alignment.svg',tolerance_pt=1.5,gutter_tolerance_pt=1.5,require_panel_labels=True,strict=True)
for ext in ['svg','pdf']:fig.savefig(D/('figure.'+ext))
fig.savefig(D/'figure.png',dpi=600)
plt.close(fig)
with (D/'source_trajectories.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(trajectories[0]));w.writeheader();w.writerows(trajectories)
from PIL import Image
im=Image.open(D/'figure.png');im.convert('L').save(D/'figure.grayscale.png')
validation={'status':'PLOTTED_ALL_FROZEN_OBSERVATIONS','paired_cell_metrics':40,'coverage_values':coverage_rows,'trajectory_rows':len(trajectories),'trajectory_cells':{cid:sum(r['cell_id']==cid for r in trajectories) for cid in p['example_cells']},'prediction_rows_read':4567,'all_points_used':True,'path_simplification':False,'no_curve_smoothing_or_window_selection':True,'linear_coverage_not_defined_not_plotted':True,'prediction_values_changed':False,'new_fits':0,'new_model_inference':0,'new_raw_feature_reads':0,'dev_test_reads':0,'figure_mm':[width_mm,height_mm],'sources_verified':True,'alignment_status':alignment.get('status',alignment.get('verdict')),'outputs':{f.name:sha(f) for f in [D/'figure.svg',D/'figure.pdf',D/'figure.png',D/'source_cell_metrics.csv',D/'source_trajectories.csv']}}
(D/'data_validation.json').write_text(json.dumps(validation,indent=2)+'\n')
print(json.dumps(validation))
