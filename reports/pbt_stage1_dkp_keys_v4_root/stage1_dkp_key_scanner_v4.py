#!/home/yndx/miniconda3/envs/a40_env/bin/python
"""Inactive, one-run-gated structural DKP key inventory. Never unpickles or decodes array payloads."""
import csv
import hashlib
import io
import json
import os
import pickletools
import resource
import signal
import stat
import struct
import sys
import time
import zlib

ROOT_PARTS = ('home', 'yndx', 'zxk', 'rul')
STAGE = 'PBT_STAGE1_DKP_KEYS_V4'
SCRIPT_REL = 'reports/pbt_stage1_dkp_keys_v4_root/stage1_dkp_key_scanner_v4.py'
SPEC_REL = 'reports/pbt_stage1_dkp_keys_v4_root/pbt_stage1_dkp_key_spec_v4.json'
GO_REL = 'reports/pbt_stage1_dkp_keys_v4_root/root_go.json'  # root-created; absent by default
PRIOR_REL = 'reports/pbt_validation_loader_candidate_v3/restricted_decode_receipt.json'
CSV_REL = 'reports/pbt_val_pairing_static_v1_luna/existing_view_join_v2/hustval15_static_pairing.csv'
ARCHIVE_REL = 'data/raw/PBT/aging_condition_prompt_embeddings.zip'
MEMBER = 'validation_DKP_embed_all_Llama.pkl'
OUT_DIR_REL = 'reports/pbt_stage1_dkp_keys_v4_root/output'  # root-created only after separate GO
OUT_NAME = 'key_presence_manifest.json'
TMP_NAME = '.key_presence_manifest.pending'
EXPECTED_MEMBER_SHA = 'de4ff4ec876361a2020b6f6b8f5f2cbbee87199b9b941958806ad7b0fdf3261a'
EXPECTED_MEMBER_CRC = 0xc1c331ee
EXPECTED_MEMBER_SIZE = 1608976
EXPECTED_KEYSET_SHA = '5a148151dd076744acff1c48400450a387135cb0a2b0a541e08f50b3c6515fe5'
EXPECTED_PRIOR_SHA = 'f6f1507589aa9f14ec1506500c150c90e87592288ea3fc215103312bbcd68912'
EXPECTED_CSV_SHA = '143710b7f7b664eb1ceb2a11c4213e9c5674a3c3de389e85132d54324afaa75d'
EXPECTED_OPS = {'BINBYTES','BINGET','BININT','BININT1','BININT2','BUILD','EMPTY_DICT','FRAME','MARK','MEMOIZE','NEWFALSE','NEWTRUE','NONE','PROTO','REDUCE','SETITEMS','SHORT_BINBYTES','SHORT_BINUNICODE','STACK_GLOBAL','STOP','TUPLE','TUPLE1','TUPLE2','TUPLE3'}
EXPECTED_GLOBALS = {('numpy.core.multiarray','_reconstruct'),('numpy','ndarray'),('numpy','dtype')}
LIMITS = {
    'max_wall_seconds': 20, 'max_cpu_seconds': 10, 'max_address_space_bytes': 268435456,
    'max_open_files': 16, 'max_output_bytes': 32768,
    'max_archive_bytes_read': 8388608, 'max_eocd_tail_bytes': 65557,
    'max_central_directory_bytes': 6291456, 'max_zip_entries': 4096,
    'max_member_compressed_bytes': 2097152, 'max_member_uncompressed_bytes': 2097152,
    'max_text_file_bytes': 65536, 'max_prior_receipt_bytes': 16384,
    'max_csv_bytes': 65536, 'max_opcode_count': 6000,
}
SPEC_REQUIRED = {
    'schema_version': 1, 'stage_id': STAGE,
    'scope': 'single-target-member structural DKP key presence and ndarray BUILD offsets; no numeric values',
    'source': {'archive_path': ARCHIVE_REL, 'archive_sha256': 'NOT_COMPUTED_BY_SCOPE', 'member': MEMBER, 'member_sha256': EXPECTED_MEMBER_SHA, 'member_crc32': '%08x' % EXPECTED_MEMBER_CRC, 'member_size_bytes': EXPECTED_MEMBER_SIZE},
    'prior_receipt': {'path': PRIOR_REL, 'sha256': EXPECTED_PRIOR_SHA, 'keyset_sha256': EXPECTED_KEYSET_SHA},
    'population': {'csv_path': CSV_REL, 'csv_sha256': EXPECTED_CSV_SHA, 'file_name_column': 'file_name', 'row_count': 15},
    'limits': LIMITS,
    'output': {'directory': OUT_DIR_REL, 'file': OUT_NAME, 'max_bytes': 32768, 'create_only_atomic': True, 'directory_created_by': 'root only after separate exact GO'},
    'authorization': {'separate_root_go_required': True, 'member_metadata_scan_only': True, 'numeric_payload_decode': False, 'model_execution': False, 'scanner_execution_authorized_now': False, 'root_go_present_now': False},
    'execution': {'stage':'INACTIVE_PREPARATION_ONLY','scanner_runs_authorized_now':0,'max_scanner_runs_after_root_GO':1,'external_root_invocation_ledger_required_before_invocation':True,'max_member_scans_after_root_GO':1,'max_candidate_member_reads_after_root_GO':1,'script_rel':'reports/pbt_stage1_dkp_keys_v4_root/stage1_dkp_key_scanner_v4.py','spec_rel':'reports/pbt_stage1_dkp_keys_v4_root/pbt_stage1_dkp_key_spec_v4.json','go_rel':'reports/pbt_stage1_dkp_keys_v4_root/root_go.json','go_template_rel':'reports/pbt_stage1_dkp_keys_v4_root/root_go_template_v4.json'},
    'expected_structural_counts': {'protocol':4,'opcode_count':4942,'BINBYTES':195,'SHORT_BINBYTES':1,'byte_string_opcode_total':196,'reduce_count':196,'build_count':196,'unique_root_keys':195,'dtype_build_state':[3,'<',None,None,None,-1,-1,0],'reconstruct_marker_hex':'62','dtype_reduce_args':['f2',False,True]}
}

class Stop(Exception):
    pass

def stop(msg):
    raise Stop(msg)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def stat_sig(st):
    # Full stat remains mandatory for opened regular-file content/replacement checks.
    return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)

def dir_sig(st):
    # Directory child creation changes size/timestamps; identity and type are stable.
    return (st.st_dev, st.st_ino, stat.S_IFMT(st.st_mode), st.st_mode,
            st.st_uid, st.st_gid)

def open_root():
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open('/', flags)
    held = [fd]
    edges = []
    prefix=[]
    try:
        for part in ROOT_PARTS:
            nxt = os.open(part, flags, dir_fd=fd)
            held.append(nxt)
            st = os.fstat(nxt)
            if not stat.S_ISDIR(st.st_mode): stop('root component is not a directory: '+part)
            prefix.append(part)
            edges.append((tuple(prefix), dir_sig(st)))
            fd = nxt
        for x in held[:-1]:
            os.close(x)
        return fd, [fd], edges
    except BaseException:
        for x in reversed(held):
            try: os.close(x)
            except OSError: pass
        raise

def parts(rel):
    p = rel.split('/')
    if not rel or rel.startswith('/') or any(x in ('', '.', '..') for x in p):
        stop('unsafe project-relative path: '+rel)
    return p

def walk_parent(rel):
    ps = parts(rel)
    rootfd, held, root_edges = open_root()
    dirs = [rootfd]
    edges = list(root_edges)
    prefix=list(ROOT_PARTS)
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = rootfd
        for comp in ps[:-1]:
            nxt = os.open(comp, flags, dir_fd=fd)
            held.append(nxt)
            st = os.fstat(nxt)
            if not stat.S_ISDIR(st.st_mode):
                stop('path component is not a directory: '+comp)
            prefix.append(comp)
            edges.append((tuple(prefix), dir_sig(st)))
            dirs.append(nxt)
            fd = nxt
        parent=dirs[-1]
        for x in reversed(held):
            if x != parent:
                try: os.close(x)
                except OSError: pass
        return parent, ps[-1], [parent], edges
    except BaseException:
        close_all(held)
        raise

def verify_edges(edges):
    flags = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    for components, expected in edges:
        fd=os.open('/',flags)
        try:
            for comp in components:
                nxt=os.open(comp,flags,dir_fd=fd)
                os.close(fd)
                fd=nxt
            st=os.fstat(fd)
            if dir_sig(st) != expected:
                stop('directory identity/type changed while open: '+'/'.join(components))
        finally:
            try: os.close(fd)
            except OSError: pass

def close_all(fds):
    for fd in reversed(fds):
        try: os.close(fd)
        except OSError: pass

def open_regular(rel):
    parent, leaf, held, edges = walk_parent(rel)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(leaf, flags, dir_fd=parent)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            os.close(fd); stop('input is not a regular file: '+rel)
        return fd, st, parent, leaf, held, edges
    except BaseException:
        close_all(held)
        raise

def verify_open_file(fd, before, parent, leaf, edges):
    if stat_sig(os.fstat(fd)) != stat_sig(before):
        stop('opened file changed during read')
    now = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
    if stat_sig(now) != stat_sig(before):
        stop('file path replaced during read')
    verify_edges(edges)

def read_small(rel, cap):
    fd, before, parent, leaf, held, edges = open_regular(rel)
    try:
        if before.st_size > cap: stop('bounded text input too large: '+rel)
        chunks=[]; total=0
        while True:
            b=os.read(fd, min(65536, cap-total+1))
            if not b: break
            total += len(b)
            if total > cap: stop('bounded text input exceeded cap: '+rel)
            chunks.append(b)
        data=b''.join(chunks)
        if len(data) != before.st_size: stop('input size changed while reading: '+rel)
        verify_open_file(fd,before,parent,leaf,edges)
        return data
    finally:
        os.close(fd); close_all(held)

class ArchiveReader:
    def __init__(self, rel):
        self.fd,self.before,self.parent,self.leaf,self.held,self.edges=open_regular(rel)
        self.total=0
    def read_at(self, offset, length):
        if offset < 0 or length < 0 or offset+length > self.before.st_size:
            stop('ZIP read outside archive bounds')
        if self.total+length > LIMITS['max_archive_bytes_read']:
            stop('archive-byte read budget exceeded')
        out=[]; pos=offset; left=length
        while left:
            b=os.pread(self.fd,min(left,65536),pos)
            if not b: stop('unexpected EOF in bounded ZIP read')
            out.append(b); pos += len(b); left -= len(b); self.total += len(b)
        return b''.join(out)
    def verify(self): verify_open_file(self.fd,self.before,self.parent,self.leaf,self.edges)
    def close(self):
        os.close(self.fd); close_all(self.held)

def extract_target_member():
    z=ArchiveReader(ARCHIVE_REL)
    try:
        size=z.before.st_size
        tail_len=min(size,LIMITS['max_eocd_tail_bytes'])
        tail=z.read_at(size-tail_len,tail_len)
        sig=b'PK\x05\x06'; eocd=None; search=len(tail)
        while True:
            i=tail.rfind(sig,0,search)
            if i<0: break
            if i+22 <= len(tail):
                vals=struct.unpack_from('<4s4H2LH',tail,i)
                clen=vals[-1]
                if i+22+clen==len(tail): eocd=(i,vals); break
            search=i
        if eocd is None: stop('classic ZIP EOCD not found or comment framing invalid')
        ei,v=eocd; eocd_abs=size-tail_len+ei
        _,disk,cd_disk,n_disk,n_total,cd_size,cd_off,comment_len=v
        if eocd_abs>=20 and z.read_at(eocd_abs-20,4)==b'PK\x06\x07': stop('ZIP64 locator present; ZIP64 unsupported')
        if disk!=0 or cd_disk!=0 or n_disk!=n_total: stop('multi-disk ZIP unsupported')
        if n_total in (0xffff,) or cd_size in (0xffffffff,) or cd_off in (0xffffffff,): stop('ZIP64 sentinel detected; STOP')
        if n_total>LIMITS['max_zip_entries']: stop('ZIP central-directory entry count cap exceeded')
        if cd_size>LIMITS['max_central_directory_bytes']: stop('ZIP central-directory byte cap exceeded')
        if cd_off+cd_size!=eocd_abs: stop('unsupported bytes between central directory and EOCD')
        cd=z.read_at(cd_off,cd_size)
        entry_fmt='<4s6H3L5H2L'; entry_size=struct.calcsize(entry_fmt)
        def check_extra(blob):
            q=0
            while q<len(blob):
                if len(blob)-q<4: stop('truncated ZIP extra-field header')
                xid,xlen=struct.unpack_from('<HH',blob,q);q+=4
                if q+xlen>len(blob): stop('ZIP extra field exceeds entry bounds')
                if xid==1: stop('ZIP64 extra field detected; STOP')
                q+=xlen
        pos=0; matches=[]; seen=0
        while pos < len(cd):
            if len(cd)-pos < entry_size: stop('truncated central-directory entry')
            fields=struct.unpack_from(entry_fmt,cd,pos)
            if fields[0]!=b'PK\x01\x02': stop('invalid central-directory signature')
            (sig0, made, needed, flags, method, mtime, mdate, crc, csize, usize,
             nlen, xlen, clen, diskno, iattr, eattr, loff)=fields
            end=pos+entry_size+nlen+xlen+clen
            if end>len(cd): stop('central-directory entry fields exceed bounds')
            name=cd[pos+entry_size:pos+entry_size+nlen]
            extra=cd[pos+entry_size+nlen:pos+entry_size+nlen+xlen]
            check_extra(extra)
            if needed>=45: stop('ZIP version-needed indicates possible ZIP64/unsupported feature')
            if diskno!=0: stop('split ZIP member unsupported')
            if csize==0xffffffff or usize==0xffffffff or loff==0xffffffff: stop('ZIP64 member sentinel detected; STOP')
            mode=(eattr>>16)&0xffff
            if name==MEMBER.encode('ascii'):
                matches.append({'flags':flags,'method':method,'crc':crc,'csize':csize,'usize':usize,'loff':loff,'name':name,'mode':mode})
            pos=end; seen+=1
            if seen>LIMITS['max_zip_entries']: stop('ZIP entry cap exceeded during parse')
        if pos!=len(cd) or seen!=n_total: stop('central-directory length/count mismatch')
        if len(matches)!=1: stop('target member missing or duplicated in bounded central directory')
        x=matches[0]
        if x['flags']&0x0041 or x['flags']&~0x080e: stop('encrypted or unsupported target general-purpose flags')
        if x['method'] not in (0,8): stop('target compression method unsupported')
        if x['usize']!=EXPECTED_MEMBER_SIZE or x['usize']>LIMITS['max_member_uncompressed_bytes']: stop('target uncompressed size mismatch/cap')
        if x['csize']>LIMITS['max_member_compressed_bytes']: stop('target compressed size cap exceeded')
        if stat.S_ISLNK(x['mode']): stop('target ZIP member is a symlink')
        if x['loff']+30>cd_off: stop('local header overlaps central directory')
        lh=z.read_at(x['loff'],30)
        lf=struct.unpack('<4s5H3L2H',lh)
        if lf[0]!=b'PK\x03\x04': stop('invalid local file-header signature')
        _,lneed,lflags,lmethod,ltime,ldate,lcrc,lcsize,lusize,lnlen,lxlen=lf
        if lflags!=x['flags'] or lmethod!=x['method']: stop('local/central ZIP flags or method mismatch')
        if lnlen>4096 or lxlen>65535: stop('local header name/extra cap exceeded')
        ltail=z.read_at(x['loff']+30,lnlen+lxlen)
        lname=ltail[:lnlen]
        check_extra(ltail[lnlen:])
        if lname!=x['name']: stop('local/central member name mismatch')
        data_off=x['loff']+30+lnlen+lxlen
        data_end=data_off+x['csize']
        if data_end>cd_off or data_end>size: stop('target compressed data overlaps central directory/archive end')
        if not (x['flags']&8) and (lcrc!=x['crc'] or lcsize!=x['csize'] or lusize!=x['usize']): stop('local/central CRC or sizes differ')
        comp=z.read_at(data_off,x['csize'])
        if x['method']==0:
            if len(comp)!=x['usize']: stop('stored member length mismatch')
            raw=comp
        else:
            decomp=zlib.decompressobj(-15)
            raw=decomp.decompress(comp,x['usize']+1)
            if len(raw)>x['usize'] or decomp.unconsumed_tail: stop('inflate output cap exceeded')
            raw+=decomp.flush()
            if len(raw)>x['usize'] or not decomp.eof or decomp.unused_data or decomp.unconsumed_tail: stop('deflate stream framing mismatch')
        if len(raw)!=EXPECTED_MEMBER_SIZE or len(raw)!=x['usize']: stop('target member exact size mismatch')
        if sha(raw)!=EXPECTED_MEMBER_SHA: stop('target member SHA-256 mismatch')
        crc_actual=zlib.crc32(raw)&0xffffffff
        if crc_actual!=EXPECTED_MEMBER_CRC or crc_actual!=x['crc']: stop('target member CRC mismatch')
        z.verify()
        return raw,{'archive_path':ARCHIVE_REL,'archive_size_bytes':size,'archive_sha256':'NOT_COMPUTED_BY_SCOPE','member':MEMBER,'member_sha256':sha(raw),'member_crc32':'%08x'%crc_actual,'member_uncompressed_bytes':len(raw),'member_compressed_bytes':x['csize'],'zip_method':x['method'],'zip_entries_examined':seen,'eocd_bytes_read':tail_len,'central_directory_bytes_read':cd_size,'archive_total_bytes_read':z.total}
    finally:
        z.close()

def require(condition,msg):
    if not condition: stop(msg)

def read_json_bounded(rel,cap):
    b=read_small(rel,cap)
    try: return json.loads(b.decode('utf-8')),b
    except Exception as e: stop('invalid bounded UTF-8 JSON '+rel+': '+type(e).__name__)

def validate_go(spec_bytes,prior_bytes,csv_bytes,script_bytes,go_bytes):
    try: spec=json.loads(spec_bytes.decode('utf-8')); go=json.loads(go_bytes.decode('utf-8'))
    except Exception as e: stop('invalid spec/root GO JSON: '+type(e).__name__)
    want={
      'stage_id':STAGE,'decision':'GO_RESTRICTED_DKP_KEY_METADATA_ONLY',
      'code_sha256':sha(script_bytes),'spec_sha256':sha(spec_bytes),
      'source_sha256':EXPECTED_MEMBER_SHA,'source_crc32':'%08x'%EXPECTED_MEMBER_CRC,
      'source_member':MEMBER,'source_archive_path':ARCHIVE_REL,
      'prior_receipt_sha256':sha(prior_bytes),'fixed_population_csv_sha256':sha(csv_bytes),
      'limits':LIMITS,'single_run_budget':{'max_scanner_runs':1,'max_member_scans':1,'max_candidate_member_reads':1},
      'authorization':{'binary_member_metadata_scan':True,'numeric_payload_decode':False,'array_value_decode':False,'model_construction':False,'strict_load':False,'forward':False,'metrics':False,'training':False,'test_access':False}}
    require(spec==SPEC_REQUIRED,'spec fields or values differ from the scanner-bound contract')
    require(go==want,'root GO must bind exact code/spec/source/receipt/CSV hashes, limits, and single-run budget')
    return spec,go

def preflight_then_open_output(spec_bytes,prior_bytes,csv_bytes,script_bytes,go_bytes,opener=None):
    spec,go=validate_go(spec_bytes,prior_bytes,csv_bytes,script_bytes,go_bytes)
    if opener is None: opener=open_output
    return spec,go,opener()

def csv_population(b):
    try: text=b.decode('utf-8-sig')
    except UnicodeDecodeError: stop('population CSV is not UTF-8')
    reader=csv.DictReader(io.StringIO(text,newline=''))
    if reader.fieldnames is None or 'file_name' not in reader.fieldnames: stop('population CSV lacks actual file_name header')
    rows=list(reader)
    if len(rows)!=15: stop('population CSV must contain exactly 15 rows')
    names=[]; stems=[]
    for row in rows:
        name=row.get('file_name')
        if not isinstance(name,str) or not name.endswith('.pkl') or '/' in name or '\\' in name or name in ('.pkl',''):
            stop('invalid fixed-population file_name value')
        stem=name[:-4]
        if not stem or stem in stems: stop('duplicate/empty filename stem')
        names.append(name);stems.append(stem)
    return names,stems

def tok(kind,**kw):
    d={'kind':kind};d.update(kw);return d

def as_tuple(t): return t.get('items',[]) if t.get('kind')=='tuple' else None

def is_token(t,kind,value=None):
    return isinstance(t,dict) and t.get('kind')==kind and (value is None or t.get('value')==value)

def apply_build_in_place(inst,state,pos):
    # Mutate the object already in memo. This preserves BINGET aliases across BUILD.
    vals=as_tuple(state)
    if inst.get('kind')=='dtype_shell':
        expected=(3,'<',None,None,None,-1,-1,0)
        if vals is None or len(vals)!=8: stop('dtype BUILD state malformed')
        actual=tuple(v.get('value') if isinstance(v,dict) else None for v in vals)
        kinds=tuple(v.get('kind') if isinstance(v,dict) else None for v in vals)
        if actual!=expected or kinds!=('int','str','none','none','none','int','int','int'):
            stop('dtype BUILD state differs from exact frozen tuple')
        inst.clear();inst.update(tok('dtype_built',dtype='f2',state=expected,offset=pos))
        return inst
    if inst.get('kind')=='array_shell':
        if vals is None or len(vals)!=5: stop('ndarray BUILD state malformed')
        version,shape,dtype,fortran,payload=vals;dims=as_tuple(shape)
        if version.get('kind')!='int' or version.get('value')!=1 or dims is None or len(dims)!=2: stop('ndarray BUILD shape/version malformed')
        if [x.get('value') for x in dims]!=[1,4096] or any(x.get('kind')!='int' for x in dims): stop('ndarray BUILD dimensions mismatch')
        if dtype.get('kind')!='dtype_built' or dtype.get('dtype')!='f2': stop('ndarray BUILD dtype mismatch')
        if fortran.get('kind')!='bool' or fortran.get('value') is not False: stop('ndarray BUILD order token mismatch')
        if payload.get('kind')!='bytes' or len(payload.get('value',b''))!=8192: stop('ndarray raw byte-length metadata mismatch')
        inst.clear();inst.update(tok('ndarray',build_offset=pos,shape=[1,4096],dtype='f2',raw_bytes_length=8192))
        return inst
    stop('BUILD instance is not an inert approved ndarray/dtype token')

def expected_dtype_args(items):
    return (len(items)==3 and is_token(items[0],'str','f2')
            and is_token(items[1],'bool',False) and is_token(items[2],'bool',True))

def valid_reconstruct_marker(token):
    return is_token(token,'bytes',b'b')

def byte_opcode_counts(raw):
    counts={'BINBYTES':0,'SHORT_BINBYTES':0}
    for op,arg,pos in pickletools.genops(io.BytesIO(raw)):
        if op.name in counts: counts[op.name]+=1
    return counts

def symbolic_inventory(raw):
    stack=[];memo={};next_memo=0;ops=[];globals_seen=[];reduce_n=0;build_n=0
    binbytes_n=0;short_binbytes_n=0;dicts=[];root_items=None
    mark=object()
    def pop():
        if not stack: stop('symbol stack underflow')
        return stack.pop()
    for op,arg,pos in pickletools.genops(io.BytesIO(raw)):
        name=op.name;ops.append(name)
        if len(ops)>LIMITS['max_opcode_count']: stop('pickle opcode-count cap exceeded')
        if name=='PROTO':
            if arg!=4: stop('pickle protocol is not exactly 4')
        elif name=='FRAME':
            if not isinstance(arg,int) or arg<0 or pos+9+arg>len(raw): stop('invalid FRAME boundary')
        elif name=='MARK': stack.append(mark)
        elif name=='EMPTY_DICT':
            d=tok('dict',items=[],offset=pos);dicts.append(d);stack.append(d)
        elif name=='SHORT_BINUNICODE': stack.append(tok('str',value=arg,offset=pos))
        elif name=='BINBYTES':
            binbytes_n+=1;stack.append(tok('bytes',value=arg,offset=pos))
        elif name=='SHORT_BINBYTES':
            short_binbytes_n+=1;stack.append(tok('bytes',value=arg,offset=pos))
        elif name in ('BININT','BININT1','BININT2'): stack.append(tok('int',value=arg,offset=pos))
        elif name=='NONE': stack.append(tok('none',offset=pos))
        elif name=='NEWTRUE': stack.append(tok('bool',value=True,offset=pos))
        elif name=='NEWFALSE': stack.append(tok('bool',value=False,offset=pos))
        elif name=='STACK_GLOBAL':
            nm=pop();mod=pop()
            if nm.get('kind')!='str' or mod.get('kind')!='str': stop('STACK_GLOBAL operands are not inert strings')
            ident=(mod['value'],nm['value']);globals_seen.append({'identity':ident,'offset':pos})
            if ident not in EXPECTED_GLOBALS: stop('unexpected STACK_GLOBAL identity')
            stack.append(tok('global',identity=ident,offset=pos))
        elif name in ('TUPLE1','TUPLE2','TUPLE3'):
            n={'TUPLE1':1,'TUPLE2':2,'TUPLE3':3}[name]
            vals=stack[-n:]
            if len(vals)!=n or any(v is mark for v in vals): stop('invalid compact tuple stack')
            del stack[-n:];stack.append(tok('tuple',items=vals,offset=pos))
        elif name=='TUPLE':
            try:i=len(stack)-1-stack[::-1].index(mark)
            except ValueError: stop('TUPLE without MARK')
            vals=stack[i+1:];del stack[i:];stack.append(tok('tuple',items=vals,offset=pos))
        elif name=='MEMOIZE':
            if not stack: stop('MEMOIZE on empty stack')
            memo[next_memo]=stack[-1];next_memo+=1
        elif name=='BINGET':
            if arg not in memo: stop('BINGET references missing memo')
            stack.append(memo[arg])
        elif name=='REDUCE':
            reduce_n+=1;args=pop();func=pop();items=as_tuple(args)
            if func.get('kind')!='global' or items is None: stop('REDUCE symbol operands malformed')
            ident=func['identity']
            if ident==('numpy.core.multiarray','_reconstruct'):
                if len(items)!=3 or items[0].get('kind')!='global' or items[0].get('identity')!=('numpy','ndarray') or as_tuple(items[1]) is None: stop('ndarray reconstruct arguments malformed')
                shape=as_tuple(items[1])
                if len(shape)!=1 or shape[0].get('kind')!='int' or shape[0].get('value')!=0 or not valid_reconstruct_marker(items[2]): stop('ndarray reconstruct token shape/marker malformed')
                stack.append(tok('array_shell',offset=pos))
            elif ident==('numpy','dtype'):
                if not expected_dtype_args(items): stop('dtype REDUCE arguments differ from exact inert f2 signature')
                stack.append(tok('dtype_shell',dtype='f2',dtype_args=('f2',False,True),offset=pos))
            else: stop('unsupported REDUCE callable')
        elif name=='BUILD':
            build_n+=1;state=pop();inst=pop()
            stack.append(apply_build_in_place(inst,state,pos))
        elif name=='SETITEMS':
            try:i=len(stack)-1-stack[::-1].index(mark)
            except ValueError: stop('SETITEMS without MARK')
            if i<1: stop('SETITEMS missing target mapping')
            mapping=stack[i-1];pairs=stack[i+1:]
            if mapping.get('kind')!='dict' or len(pairs)%2: stop('SETITEMS mapping/pairs malformed')
            if len(dicts)!=1 or mapping is not dicts[0] or i!=1: stop('SETITEMS target is not the unique root dictionary')
            items=[]
            for j in range(0,len(pairs),2):
                key,val=pairs[j],pairs[j+1]
                if key.get('kind')!='str': stop('root SETITEMS key is not a string token')
                if val.get('kind')!='ndarray': stop('root SETITEMS value is not an inert validated ndarray BUILD token')
                items.append({'key':key['value'],'key_offset':key['offset'],'array_build_offset':val['build_offset'],'value':val})
            mapping['items']=items;root_items=items;del stack[i-1:];stack.append(mapping)
        elif name=='STOP':
            if pos!=len(raw)-1 or len(stack)!=1 or stack[0].get('kind')!='dict': stop('STOP position/root stack/trailing-byte mismatch')
        else: stop('unhandled pickle opcode: '+name)
    if not ops or ops[-1]!='STOP' or root_items is None: stop('pickle stream did not produce one root SETITEMS dictionary')
    if len(dicts)!=1 or len(root_items)!=195: stop('unique root dictionary/key count mismatch')
    keys=[x['key'] for x in root_items]
    if len(set(keys))!=195: stop('root dictionary keys are not unique')
    if len(ops)!=4942 or set(ops)!=EXPECTED_OPS or reduce_n!=196 or build_n!=196 or binbytes_n!=195 or short_binbytes_n!=1: stop('opcode/reduce/build/separate byte-opcode inventory differs from bound prior receipt')
    if len(globals_seen)!=3 or {x['identity'] for x in globals_seen}!=EXPECTED_GLOBALS: stop('global identity inventory differs from bound prior receipt')
    key_sha=sha(('\n'.join(sorted(keys))).encode('utf-8'))
    if key_sha!=EXPECTED_KEYSET_SHA: stop('direct root dictionary keyset SHA differs from prior frozen value')
    return root_items,key_sha,{'protocol':4,'opcode_count':len(ops),'opcode_names':sorted(set(ops)),'stack_global_count':len(globals_seen),'globals':[{'module':x['identity'][0],'name':x['identity'][1],'offset':x['offset']} for x in globals_seen],'reduce_count':reduce_n,'build_count':build_n,'binbytes_count':binbytes_n,'short_binbytes_count':short_binbytes_n,'byte_string_opcode_count':binbytes_n+short_binbytes_n,'root_empty_dict_count':len(dicts),'root_setitems_count':1,'direct_root_key_count':len(keys),'keyset_sha256_sorted_newline':key_sha}

def open_output():
    rel=OUT_DIR_REL+'/'+OUT_NAME
    parent,leaf,held,edges=walk_parent(rel)
    try:
        # Fail closed if either the final artifact or pending file already exists.
        for nm in (leaf,TMP_NAME):
            try: os.stat(nm,dir_fd=parent,follow_symlinks=False); stop('create-only output/pending path already exists: '+nm)
            except FileNotFoundError: pass
        fd=os.open(TMP_NAME,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600,dir_fd=parent)
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode): os.close(fd);stop('pending output is not a regular file')
        marker=b'{"status":"RUNNING_NO_RESULT","stage_id":"'+STAGE.encode('ascii')+b'"}\n'
        os.write(fd,marker);os.fsync(fd)
        return fd,parent,leaf,held,edges,(st.st_dev,st.st_ino,st.st_mode),{'linked':False}
    except BaseException:
        close_all(held);raise

def publish_output(outctx,obj):
    fd,parent,leaf,held,edges,outid,pubstate=outctx
    # Once linked, this inode is immutable even on a subsequent failure path.
    if pubstate['linked'] or os.fstat(fd).st_nlink != 1:
        stop('published or multiply-linked output inode cannot be rewritten')
    raw=(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    if len(raw)>LIMITS['max_output_bytes']: stop('output byte cap exceeded')
    os.lseek(fd,0,os.SEEK_SET);os.ftruncate(fd,0)
    view=memoryview(raw)
    while view:
        n=os.write(fd,view)
        if n<=0: stop('short/zero output write')
        view=view[n:]
    os.fsync(fd)
    st=os.fstat(fd)
    if (st.st_dev,st.st_ino,st.st_mode)!=(outid[0],outid[1],outid[2]) or st.st_size!=len(raw): stop('pending output fd changed or size mismatch')
    pathst=os.stat(TMP_NAME,dir_fd=parent,follow_symlinks=False)
    if (pathst.st_dev,pathst.st_ino)!=(outid[0],outid[1]): stop('pending output path was replaced')
    verify_edges(edges)
    os.link(TMP_NAME,leaf,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
    pubstate['linked']=True
    finalst=os.stat(leaf,dir_fd=parent,follow_symlinks=False)
    if (finalst.st_dev,finalst.st_ino)!=(outid[0],outid[1]): stop('atomic final link identity mismatch')
    verify_edges(edges)
    os.fsync(parent);os.unlink(TMP_NAME,dir_fd=parent);os.fsync(parent);verify_edges(edges)

def arm_wall_timer(seconds):
    signal.signal(signal.SIGALRM,lambda signum,frame: os._exit(124))
    signal.alarm(max(1,int(seconds)) if seconds>=1 else 1)

def cancel_wall_timer():
    signal.alarm(0)

def main():
    started=time.monotonic();deadline=started+20;outctx=None
    arm_wall_timer(20)
    try:
        if sys.version_info[:2]!=(3,9) or sys.flags.isolated!=1 or sys.flags.no_site!=1:
            raise Stop('must run with designated Python 3.9 using -I -S')
        resource.setrlimit(resource.RLIMIT_CPU,(10,10))
        resource.setrlimit(resource.RLIMIT_AS,(268435456,268435456))
        resource.setrlimit(resource.RLIMIT_FSIZE,(32768,32768))
        resource.setrlimit(resource.RLIMIT_NOFILE,(16,16))
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        script=read_small(SCRIPT_REL,65536);spec_bytes=read_small(SPEC_REL,65536)
        prior_bytes=read_small(PRIOR_REL,16384);csv_bytes=read_small(CSV_REL,65536);go_bytes=read_small(GO_REL,65536)
        expected_script_path='/'+'/'.join(ROOT_PARTS)+'/'+SCRIPT_REL
        if __file__!=expected_script_path: stop('scanner must be invoked from the fixed project path')
        if sha(prior_bytes)!=EXPECTED_PRIOR_SHA: stop('prior restricted receipt SHA mismatch')
        if sha(csv_bytes)!=EXPECTED_CSV_SHA: stop('fixed 15-cell CSV SHA mismatch')
        spec,go,outctx=preflight_then_open_output(spec_bytes,prior_bytes,csv_bytes,script,go_bytes)
        prior=json.loads(prior_bytes.decode('utf-8'))
        pf=prior.get('static_preflight',{})
        if pf.get('protocol')!=4 or pf.get('opcode_count')!=4942 or pf.get('stack_global_count')!=3 or pf.get('static_keyset_sha256_sorted_newline')!=EXPECTED_KEYSET_SHA:
            stop('prior structural key/opcode receipt differs from frozen static values')
        names,stems=csv_population(csv_bytes)
        raw,member_meta=extract_target_member()
        items,key_sha,inventory=symbolic_inventory(raw)
        by_key={x['key']:x for x in items}
        rows=[]
        for name,stem in zip(names,stems):
            item=by_key.get(stem)
            rows.append({'file_name':name,'filename_stem':stem,'key':stem,'present':item is not None,'array_build_offset':item['array_build_offset'] if item else None})
        if time.monotonic()>deadline-2.0: stop('less than two seconds remain for bounded atomic publication')
        result={'schema_version':1,'status':'STATIC_DKP_ROOT_KEY_PRESENCE_AND_ARRAY_BUILD_OFFSETS_ONLY','stage_id':STAGE,'go_sha256':sha(go_bytes),'spec_sha256':sha(spec_bytes),'scanner_code_sha256':sha(script),'prior_receipt_sha256':sha(prior_bytes),'fixed_population_csv_sha256':sha(csv_bytes),'source':member_meta,'structural_inventory':inventory,'population_count':len(rows),'cells':rows,'values_emitted':False,'numeric_payload_decode':False,'ndarray_values_decoded':0,'pickle_unpickler_used':False,'numpy_imported':False,'model_construction':False,'strict_load':False,'forward':False,'metrics':False,'training':False,'optimizer_steps':0,'test_access':False,'elapsed_wall_seconds':round(time.monotonic()-started,6),'budget':LIMITS,'execution_count_authorized':1}
        publish_output(outctx,result)
        close_all(outctx[3]);os.close(outctx[0]);outctx=None
        cancel_wall_timer()
        return 0
    except BaseException as e:
        failure={'schema_version':1,'status':'STOP_RESTRICTED_DKP_SCAN_FAILED','stage_id':STAGE,'error_type':type(e).__name__,'error':str(e)[:1000],'no_numeric_payload_decode':True,'no_model_execution':True,'budget':LIMITS}
        if outctx is not None:
            # A post-link error is reported by exit/root receipt; preserve published bytes.
            try:
                if not outctx[6]['linked']: publish_output(outctx,failure)
            except BaseException: pass
            try: os.close(outctx[0]);close_all(outctx[3])
            except BaseException: pass
        cancel_wall_timer()
        if isinstance(e,KeyboardInterrupt): raise
        print('STOP: '+type(e).__name__+': '+str(e),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
