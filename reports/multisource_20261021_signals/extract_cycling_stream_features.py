#!/usr/bin/env python3
# Streaming summary extractor for one authorized ISU-ILCC Cycling_json ZIP member.
import sys, os, json, hashlib, pathlib, struct, zlib, datetime, math, codecs, gzip
ROOT=pathlib.Path('/home/yndx/zxk/rul')
PLAN=ROOT/'reports/multisource_20261021_root/cycling_members_plan.json'
GO=ROOT/'reports/multisource_20261021_signals/CYCLING_EXTRACT_ALL_GO.json'
OUT=ROOT/'reports/multisource_20261021_signals/cycling_features_v3'
CHUNK=1<<20

class Stream:
    def __init__(self, f, limit): self.f=f; self.limit=limit; self.n=0; self.buf=b''; self.i=0
    def _fill(self):
        if self.i < len(self.buf): return
        b=self.f.read(CHUNK)
        if not b: self.buf=b''; self.i=0; return
        self.n+=len(b); assert self.n<=self.limit, 'inflate_cap_exceeded'
        self.buf=b; self.i=0
    def peek(self): self._fill(); return self.buf[self.i:self.i+1]
    def get(self): self._fill(); c=self.buf[self.i:self.i+1]; self.i+=bool(c); return c
    def ws(self):
        while self.peek() in (b' ',b'\n',b'\r',b'\t'): self.get()
    def string(self):
        quote=bytes([34]); slash=bytes([92]); assert self.get()==quote; out=bytearray(quote); esc=False
        while True:
            c=self.get(); assert c, 'truncated_string'; out+=c
            if esc: esc=False
            elif c==slash: esc=True
            elif c==quote: break
        return json.loads(out.decode('utf-8'))
    def scalar(self):
        self.ws(); c=self.peek()
        if c==bytes([34]): return self.string()
        b=bytearray()
        while self.peek() and self.peek() not in (b',',b']',b'}',b' ',b'\n',b'\r',b'\t'): b+=self.get()
        return json.loads(b.decode('ascii'))
    def skip(self):
        self.ws(); c=self.peek()
        if c==b'{':
            self.get(); self.ws()
            if self.peek()==b'}': self.get(); return
            while True:
                self.ws(); self.string(); self.ws(); assert self.get()==b':'; self.skip(); self.ws(); x=self.get()
                if x==b'}': return
                assert x==b','
        elif c==b'[':
            self.get(); self.ws()
            if self.peek()==b']': self.get(); return
            while True:
                self.skip(); self.ws(); x=self.get()
                if x==b']': return
                assert x==b','
        else: self.scalar()
    def arr_stats(self, keep=False):
        self.ws(); assert self.get()==b'['; self.ws(); out=[]; n=0; lo=hi=sm=None; first=last=None
        if self.peek()==b']': self.get(); return out if keep else {'n':0}
        while True:
            v=self.scalar(); n+=1
            if keep: out.append(v)
            if isinstance(v,(int,float)) and math.isfinite(v):
                first=v if first is None else first; last=v; lo=v if lo is None else min(lo,v); hi=v if hi is None else max(hi,v); sm=(sm or 0.0)+v
            self.ws(); c=self.get()
            if c==b']': break
            assert c==b','
        if keep: return out
        return {'n':n,'first':first,'last':last,'min':lo,'max':hi,'mean':(sm/n if sm is not None and n else None)}
    def nested_stats(self):
        self.ws(); assert self.get()==b'['; self.ws(); out=[]
        if self.peek()==b']': self.get(); return out
        while True:
            out.append(self.arr_stats(False)); self.ws(); c=self.get()
            if c==b']': return out
            assert c==b','
    def time_obj(self):
        self.ws(); assert self.get()==b'{'; out={}; self.ws()
        if self.peek()==b'}': self.get(); return out
        while True:
            k=self.string(); self.ws(); assert self.get()==b':'
            if k in ('start','stop'): out[k]=self.arr_stats(True)
            else: self.skip()
            self.ws(); c=self.get()
            if c==b'}': return out
            assert c==b','
    def qv_obj(self):
        self.ws(); assert self.get()==b'{'; out={}; self.ws()
        if self.peek()==b'}': self.get(); return out
        while True:
            k=self.string(); self.ws(); assert self.get()==b':'
            if k in ('Q','V','t','E','I'): out[k]=self.nested_stats()
            else: self.skip()
            self.ws(); c=self.get()
            if c==b'}': return out
            assert c==b','
    def root(self):
        self.ws()
        # Source has been observed as an object; fail closed on a wrapped JSON string.
        assert self.peek()==b'{', 'root_must_be_object'
        self.get(); out={}; self.ws()
        if self.peek()==b'}': self.get(); return out
        while True:
            k=self.string(); self.ws(); assert self.get()==b':'
            if k in ('capacity_charge','capacity_discharge'): out[k]=self.arr_stats(True)
            elif k in ('QV_charge','QV_discharge'): out[k]=self.qv_obj()
            elif k in ('time_series_charge','time_series_discharge','start_stop_time'): out[k]=self.time_obj()
            else: self.skip()
            self.ws(); c=self.get()
            if c==b'}': self.ws(); assert not self.peek(), 'trailing_json'; return out
            assert c==b','

def main():
    assert len(sys.argv)==2, 'usage: script CELL_ID'
    cid=sys.argv[1]; go=json.loads(GO.read_text()); plan=json.loads(PLAN.read_text()); m=next(x for x in plan if x['cell_id']==cid)
    state=json.loads((ROOT/'automation/state/coordinator.json').read_text());assert state['owner']==go['owner_thread_id'] and state['state']=='ACTIVE' and state['takeover_verified'] is True
    assert go.get('status')=='APPROVED' and go.get('extractor_sha256')==hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    assert go.get('plan_sha256')==hashlib.sha256(PLAN.read_bytes()).hexdigest()
    assert m['role'] in ('train','development') and not cid.endswith('C4') and cid in go['cell_ids']
    selected=[x for x in plan if x['cell_id'] in go['cell_ids']]
    assert len(selected)==len(set(go['cell_ids'])) and all(x['role'] in ('train','development') and not x['cell_id'].endswith('C4') for x in selected)
    assert sum(x['compressed_bytes'] for x in selected)<=int(go['max_total_compressed_bytes'])
    assert sum(x['bytes'] for x in selected)<=int(go['max_total_inflated_bytes'])
    cache=pathlib.Path(go['cache_dir_by_cell'][cid]);assert cache.parent==ROOT/'data/raw'
    inp=cache/(cid+'.range2.bin'); hdr=cache/(cid+'.header.bin')
    recp=cache/(cid+'.receipt.json'); receipt=json.loads(recp.read_text())
    assert receipt['GO_request']==go['cache_request_by_cell'][cid]
    assert receipt.get('status')=='COMPRESSED_CACHE_COMPLETE_NOT_DECODED' and receipt.get('cell_id')==cid and receipt.get('compressed_sha256')
    assert inp.stat().st_size==m['compressed_bytes']+struct.unpack('<4s5H3I2H',hdr.read_bytes())[-2]+struct.unpack('<4s5H3I2H',hdr.read_bytes())[-1]
    limit=int(go['max_member_inflated_bytes']); assert m['bytes']<=limit
    h=hdr.read_bytes(); a=struct.unpack('<4s5H3I2H',h); nl,xl=a[-2:]; assert len(h)==30 and a[0]==b'PK\x03\x04' and a[3]==8; fcheck=inp.open('rb'); assert fcheck.read(nl).decode()==m['name']; fcheck.close()
    # Stream the raw-deflate member; never materialize inflated JSON text.
    sys.path.insert(0, str(ROOT/'reports/multisource_20261021_signals/vendor'))
    import ijson
    class Inflated:
        def __init__(self, path, offset):
            self.f=path.open('rb'); self.comp_sha=hashlib.sha256(); prefix=self.f.read(offset); assert len(prefix)==offset; self.comp_sha.update(prefix); self.z=zlib.decompressobj(-15)
            self.comp_pending=b''; self.pending=b''; self.eof=False; self.crc=0; self.n=0; self.sha=hashlib.sha256()
        def read(self, n=-1):
            if n is None or n<0: n=CHUNK
            while len(self.pending)<n and not self.eof:
                if self.comp_pending:
                    b=self.comp_pending; self.comp_pending=b''
                else:
                    b=self.f.read(CHUNK)
                    if b: self.comp_sha.update(b)
                if not b:
                    x=self.z.flush(); self.pending+=x; self.crc=zlib.crc32(x,self.crc); self.sha.update(x); self.n+=len(x); self.eof=True
                    break
                x=self.z.decompress(b,CHUNK); self.comp_pending=self.z.unconsumed_tail
                self.pending+=x; self.crc=zlib.crc32(x,self.crc); self.sha.update(x); self.n+=len(x); assert self.n<=limit
                if self.z.eof: self.eof=True
            x,self.pending=self.pending[:n],self.pending[n:]
            return x
    src=Inflated(inp,nl+xl)
    class JSONEnvelope:
        # Source files may be a JSON string encoding a JSON object. Decode its
        # ASCII escaped envelope incrementally; never materialize the whole text.
        def __init__(self,source):
            self.source=source;self.first=True;self.wrapped=None;self.tail=b'';self.pending=b'';self.done=False
            self.decoder=codecs.getincrementaldecoder('unicode_escape')('strict')
        def read(self,n=-1):
            if n==0:return b''
            if n<0:n=CHUNK
            while len(self.pending)<n and not self.done:
                b=self.source.read(CHUNK)
                if self.first:
                    self.first=False;b=b.lstrip();self.wrapped=b[:1]==b'"'
                    assert self.wrapped or b[:1]==b'{','unrecognized_json_envelope'
                    if self.wrapped:b=b[1:]
                if not self.wrapped:
                    self.pending+=b
                    if not b:self.done=True
                    continue
                assert all(c<128 for c in b),'nonASCII_outer_envelope_requires_explicit_decoder'
                self.tail+=b
                if b:
                    body,self.tail=self.tail[:-32],self.tail[-32:]
                    self.pending+=self.decoder.decode(body,final=False).encode('utf8')
                else:
                    body=self.tail.rstrip();assert body[-1:]==b'"','unterminated_outer_json_string'
                    self.pending+=self.decoder.decode(body[:-1],final=True).encode('utf8');self.tail=b'';self.done=True
            answer,self.pending=self.pending[:n],self.pending[n:]
            return answer
    reader=JSONEnvelope(src)
    data={'capacity_charge':[],'capacity_discharge':[],'QV_charge':{},'QV_discharge':{},
          'time_series_charge':{'start':[],'stop':[]},'time_series_discharge':{'start':[],'stop':[]}}
    current={}
    array_prefix={f'QV_{leg}.{key}.item':(leg,key) for leg in ('charge','discharge') for key in ('Q','V','t','E','I')}
    leaf_prefix={p+'.item':k for p,k in array_prefix.items()}
    time_prefix={f'time_series_{leg}.{key}.item':(f'time_series_{leg}',key) for leg in ('charge','discharge') for key in ('start','stop')}
    cap_prefix={k+'.item':k for k in ('capacity_charge','capacity_discharge')}
    for prefix,event,value in ijson.parse(reader,use_float=True):
        pair=leaf_prefix.get(prefix)
        if pair is not None and event in ('number','string','null'):
            st=current[pair];st['n']+=1
            if event=='number' and math.isfinite(value):
                st['finite_n']+=1;st['first']=value if st['first'] is None else st['first'];st['last']=value
                st['min']=value if st['min'] is None else min(st['min'],value);st['max']=value if st['max'] is None else max(st['max'],value);st['sum']+=value
            elif event=='string':
                st['first']=value if st['first'] is None else st['first'];st['last']=value
            continue
        pair=array_prefix.get(prefix)
        if pair is not None:
            if event=='start_array':current[pair]={'n':0,'finite_n':0,'first':None,'last':None,'min':None,'max':None,'sum':0.0}
            elif event=='end_array':
                st=current.pop(pair);st['mean']=st.pop('sum')/st['finite_n'] if st['finite_n'] else None
                st.pop('sum',None);data['QV_'+pair[0]].setdefault(pair[1],[]).append(st)
            continue
        pair=time_prefix.get(prefix)
        if pair is not None and event in ('string','null'):data[pair[0]][pair[1]].append(value)
        elif prefix in cap_prefix and event in ('number','null'):data[cap_prefix[prefix]].append(value)
    while reader.read(CHUNK): pass
    assert src.n==m['bytes'] and src.eof and (src.crc&0xffffffff)==int(m['crc32'],16) and src.comp_sha.hexdigest()==receipt['compressed_sha256']
    # Assemble cycle records, retaining exact source indices and only scalar signal summaries.
    qc=data.get('QV_charge',{}); qd=data.get('QV_discharge',{}); tc=data.get('time_series_charge',{}); td=data.get('time_series_discharge',{})
    capc=data.get('capacity_charge',[]); capd=data.get('capacity_discharge',[])
    n=max([len(capc),len(capd)]+[len(qc.get(k,[])) for k in ('Q','V','t','E','I')]+[len(qd.get(k,[])) for k in ('Q','V','t','E','I')]+[len(tc.get('start',[])),len(td.get('start',[]))])
    assert n>0 and len(capc)==len(capd) and capc,'zero_or_mismatched_cycle_capacity_vector'
    rows=[]
    for i in range(n):
        r={'cell_id':cid,'source_cycle_index':i,'source_visible_at':None,'charge':{},'discharge':{},'capacity_charge_source_units_unknown':capc[i] if i<len(capc) else None,'capacity_discharge_source_units_unknown':capd[i] if i<len(capd) else None}
        stamps=[]
        for leg,qv,tobj in (('charge',qc,tc),('discharge',qd,td)):
            sig={k:(v[i] if i<len(v) else None) for k,v in qv.items()}
            r[leg]={'start':tobj.get('start',[None]*(i+1))[i] if i<len(tobj.get('start',[])) else None,'stop':tobj.get('stop',[None]*(i+1))[i] if i<len(tobj.get('stop',[])) else None,'Q_sample_stats':sig.get('Q'),'V_V_sample_stats':sig.get('V'),'t_sample_stats':sig.get('t'),'E_sample_stats':sig.get('E'),'I_A_sample_stats':sig.get('I')}
            if r[leg]['stop']: stamps.append(r[leg]['stop'])
        r['source_visible_at']=max(stamps) if stamps else None
        qvals=[v for v in (r['capacity_charge_source_units_unknown'],r['capacity_discharge_source_units_unknown']) if isinstance(v,(int,float)) and math.isfinite(v)]
        r['observed_cycle_throughput_source_units']=sum(qvals) if len(qvals)==2 else None
        rows.append(r)
    OUT.mkdir(parents=True,exist_ok=True); out=OUT/(cid+'.json.gz'); tmp=out.with_suffix('.gz.tmp'); assert not out.exists() and not tmp.exists(), 'output_exists_refuse_overwrite'
    existing=sum(p.stat().st_size for p in OUT.glob('*.json.gz') if p.is_file())
    assert existing < int(go['max_feature_output_bytes']), 'feature_output_cap_exceeded'
    with gzip.open(tmp,'xt',encoding='utf8',compresslevel=3) as f:
        json.dump({'cell_id':cid,'role':m['role'],'source_member':m['name'],'compressed_member_sha256':receipt['compressed_sha256'],'source_uncompressed_sha256':src.sha.hexdigest(),'source_uncompressed_bytes':src.n,'cycle_count':len(rows),'time_basis':'source per-leg start/stop ISO strings; no synthetic clock; communication arrival unobserved','throughput_basis':'sum of observed charge and discharge capacity per cycle, only when both are present; gaps/RPT are not imputed','units':'Official README V2 page5: capacity/Q Ah, E Wh, I A, V V. Historical source_units_unknown field names retained for schema compatibility. No scaling or imputation.','cycles':rows},f,separators=(',',':'),allow_nan=False)
    assert tmp.stat().st_size+existing <= int(go['max_feature_output_bytes']), 'feature_output_cap_exceeded'
    os.replace(tmp,out)
    print(json.dumps({'status':'SUCCESS','cell_id':cid,'role':m['role'],'cycles':len(rows),'inflated_bytes':src.n,'source_crc32':m['crc32'],'output_bytes':out.stat().st_size,'output_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'output':str(out)}))
if __name__=='__main__': main()
