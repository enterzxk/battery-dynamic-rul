import re
NUM=r'(\d+(?:\.\d+)?)'
def encode_policy(text):
 m=re.fullmatch(NUM+r'C\('+NUM+r'%\)-'+NUM+r'C',text)
 if m:
  c1,split,c2=map(float,m.groups());assert c1>0 and c2>0 and 0<=split<=80;segments=[(0.,split/100,c1),(split/100,.8,c2)];kind='two_stage'
 else:
  m=re.fullmatch(NUM+'-'+NUM+'-'+NUM+'-'+NUM,text);assert m is not None,'Unknown policy format: '+text
  currents=list(map(float,m.groups()));assert all(x>0 for x in currents);segments=[(i*.2,(i+1)*.2,c) for i,c in enumerate(currents)];kind='four_stage'
 values=[]
 for j in range(4):
  a,b=j*.2,(j+1)*.2;hours=sum(max(0.,min(b,y)-max(a,x))/c for x,y,c in segments);assert hours>0;values.append(.2/hours)
 total_hours=sum((b-a)/c for a,b,c in segments);assert abs(sum(.2/c for c in values)-total_hours)<1e-12
 return kind,values,60*total_hours
