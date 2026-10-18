import re
from fractions import Fraction as F
def schedule(text):
 num=r'(\d+(?:\.\d+)?)';m=re.fullmatch(num+r'C\('+num+r'%\)-'+num+r'C',text)
 if m:
  a,s,b=map(F,m.groups());s/=100;parts=[(F(0),s,a),(s,F(4,5),b)]
 else:
  m=re.fullmatch(num+'-'+num+'-'+num+'-'+num,text);assert m;cs=list(map(F,m.groups()));parts=[(F(i,5),F(i+1,5),c) for i,c in enumerate(cs)]
 merged=[]
 for a,b,c in parts:
  assert c>0 and a<=b
  if a==b:continue
  if merged and merged[-1][2]==c:merged[-1]=(merged[-1][0],b,c)
  else:merged.append((a,b,c))
 assert 1<=len(merged)<=4 and merged[0][0]==0 and merged[-1][1]==F(4,5)
 return tuple(merged)
def encode(text):
 parts=schedule(text);currents=[c for a,b,c in parts];switches=[b for a,b,c in parts[:-1]]
 currents+= [currents[-1]]*(4-len(currents));switches+=[F(4,5)]*(3-len(switches))
 return [float(v) for v in currents+switches]
def decode(vector):
 currents=list(map(lambda x:F(str(x)),vector[:4]));ends=list(map(lambda x:F(str(x)),vector[4:]))+[F(4,5)];starts=[F(0)]+ends[:-1];out=[]
 for a,b,c in zip(starts,ends,currents):
  assert a<=b and c>0
  if a==b:continue
  if out and out[-1][2]==c:out[-1]=(out[-1][0],b,c)
  else:out.append((a,b,c))
 return tuple(out)
