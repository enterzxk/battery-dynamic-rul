import re,datetime,math,itertools
FIELDS={'data_point':'datapoint','time_s':'testtimes','datetime':'datetime','step_time_s':'steptimes','step':'stepindex','cycle':'cycleindex','current_A':'currenta','voltage_V':'voltagev','charge_counter_Ah':'chargecapacityah','discharge_counter_Ah':'dischargecapacityah'}
def norm(x):return re.sub('[^a-z0-9]','',str(x).lower())
def identify(workbook):
 schemas=[];candidates=[]
 for ws in workbook.worksheets:
  ws.reset_dimensions();headers=list(itertools.islice(ws.iter_rows(values_only=True),20));found=[]
  for rownum,row in enumerate(headers,1):
   ns=[norm(x) for x in row]
   if 'datapoint' in ns and 'stepindex' in ns:
    mapping={}
    for key,token in FIELDS.items():
     indexes=[i for i,x in enumerate(ns) if x==token]
     if len(indexes)!=1:raise ValueError('AMBIGUOUS_OR_MISSING '+ws.title+' '+key+' '+str(indexes))
     mapping[key]=indexes[0]
    found.append((ws.title,rownum,mapping))
  schemas.append({'sheet':ws.title,'headers':[[str(v) if v is not None else None for v in row] for row in headers[:1]],'raw_measurement_candidates':len(found)})
  candidates+=found
 if len(candidates)!=1:raise ValueError('AMBIGUOUS_RAW_MEASUREMENT_SHEET '+str(candidates))
 return candidates[0],schemas
def records(workbook,selected,maxrows=100000):
 name,header,mapping=selected;ws=workbook[name];ws.reset_dimensions();lastpoint=None;lasttime=None
 for n,row in enumerate(ws.iter_rows(min_row=header+1,values_only=True),header+1):
  if n-header>maxrows:raise ValueError('ROW_CAP')
  if len(row)>64:raise ValueError('COLUMN_CAP')
  if all(x is None for x in row):continue
  item={}
  for k,i in mapping.items():
   v=row[i]
   if k=='datetime':
    if not isinstance(v,datetime.datetime):raise ValueError('NON_DATETIME')
    item[k]=v.isoformat()
   else:
    v=float(v)
    if not math.isfinite(v):raise ValueError('NONFINITE '+k)
    if k in ['data_point','step','cycle']:
     if not v.is_integer():raise ValueError('NONINTEGER '+k)
     v=int(v)
    item[k]=v
  if lastpoint is not None and item['data_point']<=lastpoint:raise ValueError('POINT_NONINCREASING')
  if lasttime is not None and item['time_s']<lasttime:raise ValueError('TIME_DECREASE')
  lastpoint=item['data_point'];lasttime=item['time_s'];item['source_row']=n;yield item
