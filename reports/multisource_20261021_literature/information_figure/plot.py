"""Completed nested RPT pilot, not the formal RPT x Cycling factorial."""
import sys,pathlib,json,csv,hashlib
R=pathlib.Path('/home/yndx/zxk/rul');D=R/'reports/multisource_20261021_literature/information_figure'
sys.path.insert(0,str(D/'qa_scripts'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from audit_panel_alignment import require_matplotlib_panel_alignment
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],'font.size':6.5,'axes.titlesize':7.5,'axes.labelsize':7,'xtick.labelsize':6.5,'ytick.labelsize':6.5,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'xtick.major.width':.6,'ytick.major.width':.6})
summary=list(csv.DictReader((D/'figure_source_summary.csv').open()))
paired=list(csv.DictReader((D/'figure_source_paired.csv').open()))
arms=['raw','sparse2','delay7d'];labs=['Full RPT','Sparse RPT','7-day delay'];colors=['#7A8793','#DAA35D','#397F9A'];levels=['F0','F1','F2']
contract={'claim':'Raw RPT curve history adds development information beyond 74 summary features, with cell-level heterogeneity.','archetype':'quantitative grid','backend':'Python matplotlib; existing Python experimental workflow','panel_roles':{'a':'HGB information-level average error','b':'CatBoost independent model family information-level error','c':'all61 paired HGB per-cell effects','d':'all61 paired CatBoost per-cell effects'},'scope':'Nested RPT pilot only. Formal F0/F1/F2/F3 2x2 not completed. One seed, C3 development; no independent confirmation.','source':'frozen saved predictions, no models/raw data','dimensions_mm':[183,118],'uncertainty':'bottom panels show each cell and mean with 95percent paired-cell bootstrap interval,10000 resamples seed20261021. Top panels aggregate same61 observed-event cells and show no seed uncertainty; this is a descriptive single-seed aggregate.'}
(D/'figure_contract.json').write_text(json.dumps(contract,indent=2))
fig,axs=plt.subplots(2,2,figsize=(183/25.4,118/25.4),gridspec_kw={'hspace':.55,'wspace':.33})
for col,method in enumerate(['hgb','catboost']):
 ax=axs[0,col]
 for k,level in enumerate(levels):
  vals=[float(next(r for r in summary if r['model']==method and r['arm']==a and r['level']==level)['cell_macro_MAE_weeks']) for a in arms]
  ax.scatter(np.arange(3)+(k-1)*.19,vals,s=22,c=colors[k],marker=['o','s','^'][k],label=['74 summary','+ RPT capacities','+ RPT curves'][k],zorder=3)
 ax.set(xlim=(-.5,2.5),ylim=(0,2.85),xticks=range(3),xticklabels=labs,ylabel='Cell-macro RUL MAE (weeks)',title=method.upper() if method=='hgb' else 'CatBoost')
 ax.set_yticks([0,1,2]);ax.grid(axis='y',color='.92',lw=.5,zorder=0)
 if col==0:ax.legend(loc='upper left',fontsize=5.6,frameon=False,ncol=1,handletextpad=.25,labelspacing=.25)
 ax=axs[1,col];rng=np.random.RandomState(20261021)
 for k,a in enumerate(arms):
  rr=sorted([r for r in paired if r['model']==method and r['arm']==a],key=lambda r:r['cell_id'])
  values=np.asarray([float(r['improvement_F0_minus_F2_weeks']) for r in rr]);assert len(values)==61
  jitter=(np.arange(len(values))%9-4)*.017
  ax.scatter(k+jitter,values,s=5,c=colors[2],alpha=.45,edgecolors='none',zorder=2)
  draws=values[rng.randint(0,len(values),(10000,len(values)))].mean(1);lo,hi=np.quantile(draws,[.025,.975]);mean=values.mean()
  ax.errorbar(k+.21,mean,yerr=[[mean-lo],[hi-mean]],fmt='D',color='#242424',markersize=3.2,capsize=2,lw=.8,zorder=4)
 ax.axhline(0,color='.5',ls='--',lw=.65);ax.set(xlim=(-.5,2.5),xticks=range(3),xticklabels=labs,ylabel='Per-cell MAE reduction (weeks)',ylim=(-5.2,5.2));ax.set_yticks([-4,-2,0,2,4]);ax.grid(axis='y',color='.94',lw=.5,zorder=0)
for letter,ax in zip('abcd',axs.flat):ax.text(-.16,1.08,letter,transform=ax.transAxes,fontweight='bold',fontsize=8,ha='left',va='bottom')
fig.subplots_adjust(left=.1,right=.985,bottom=.14,top=.94)
fig.text(.1,.035,'Nested RPT pilot | 61 observed-event C3 cells | seed 42 | dots: cells; diamonds: mean and 95% paired-cell CI',fontsize=6)
fig.canvas.draw();require_matplotlib_panel_alignment(fig,json_out=D/'alignment.json',tolerance_pt=1.5)
fig.savefig(D/'rpt_information_pilot.pdf')
fig.savefig(D/'rpt_information_pilot.svg')
fig.savefig(D/'rpt_information_pilot.png',dpi=300)
plt.close(fig)
print('figure exported')
