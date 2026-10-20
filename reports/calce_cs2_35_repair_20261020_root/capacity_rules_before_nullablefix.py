import hashlib,json
import math,statistics
def derive(rows,source,T):
 groups=[]
 for v in rows:
  if not groups or groups[-1][0]!=v['cycle']:groups.append((v['cycle'],[]))
  groups[-1][1].append(v)
 result=[]
 for occ,(cyc,rr) in enumerate(groups):
  fingerprint=hashlib.sha256(json.dumps([{k:v for k,v in x.items() if k!='source_row'} for x in rr],sort_keys=True).encode()).hexdigest()
  base={'measurement_fingerprint_sha256':fingerprint,'source_file':source,'source_cycle':cyc,'source_occurrence':occ,'source_rows':len(rr),'start_datetime':rr[0]['datetime'],'end_datetime':rr[-1]['datetime'],'first_source_row':rr[0]['source_row'],'last_source_row':rr[-1]['source_row']}
  neg=[j for j,v in enumerate(rr) if v['current_A'] < -T['active_current_A']]
  if not neg:base.update(status='UNCERTAIN',flags=['no_main_discharge']);result.append(base);continue
  a,b=neg[0],neg[-1];ss=rr[a:b+1];flags=[]
  if len(neg)!=len(ss) or len({v['step'] for v in ss})!=1:flags.append('multiple_or_interrupted_main_discharge')
  prev=rr[a-1] if a else None;charge=[v for v in rr[:a] if v['current_A']>T['active_current_A']]
  if not prev or abs(prev['current_A'])>T['active_current_A']:flags.append('rest_baseline_missing')
  if not charge or charge[-1]['voltage_V']<T['charge_voltage_min_V'] or charge[-1]['current_A']>T['charge_tail_max_A']:flags.append('complete_charge_tail_unverified')
  if not T['discharge_voltage_min_V']<=ss[-1]['voltage_V']<=T['discharge_voltage_max_V']:flags.append('cutoff_sample_unverified')
  times=[v['time_s'] for v in ss];steps=[v['step_time_s'] for v in ss];currents=[-v['current_A'] for v in ss]
  if not T['discharge_current_min_A']<=statistics.median(currents)<=T['discharge_current_max_A'] or max(currents)-min(currents)>T['max_current_spread_A']:flags.append('CC_1C_unverified')
  if any(v-u<=0 or v-u>T['max_sampling_gap_s'] for u,v in zip(times,times[1:])) or steps[0]<0 or steps[0]>T['max_sampling_gap_s']:flags.append('sampling_gap_or_step_start_unverified')
  if any(v<u for u,v in zip(steps,steps[1:])):flags.append('step_time_reset')
  if prev and abs(times[0]-steps[0]-prev['time_s'])>T['step_start_boundary_abs_gap_s']:flags.append('step_start_not_adjacent_to_baseline')
  counters=[v['discharge_counter_Ah'] for v in ss]
  if any(v-u < -1e-7 for u,v in zip(([prev['discharge_counter_Ah']] if prev else [])+counters, counters if prev else counters[1:])):flags.append('counter_reset_inside_discharge')
  partial=sum(-(u['current_A']+v['current_A'])/2*(v['time_s']-u['time_s'])/3600 for u,v in zip(ss,ss[1:]) if u['current_A']<-.01 and v['current_A']<-.01)
  qi=-ss[0]['current_A']*ss[0]['step_time_s']/3600+partial;qc=ss[-1]['discharge_counter_Ah']-prev['discharge_counter_Ah'] if prev else None
  if qc is None or qc<=0 or abs(qc-qi)>max(T['integral_absolute_tolerance_Ah'],T['integral_relative_tolerance']*(qc or 0)):flags.append('counter_integral_disagree_or_unknown')
  legacy_neg=[v for v in rr if v['current_A']<-.001]
  legacy_partial=sum(-(u['current_A']+v['current_A'])/2*(v['time_s']-u['time_s'])/3600 for u,v in zip(rr,rr[1:]) if u['current_A']<-.001 and v['current_A']<-.001)
  base['legacy_end_counter_Ah']=legacy_neg[-1]['discharge_counter_Ah'] if legacy_neg else None
  base.update(status='VALID_SAMPLED_CC_DISCHARGE' if not flags else 'UNCERTAIN',flags=flags,step=ss[0]['step'],discharge_first_source_row=ss[0]['source_row'],discharge_last_source_row=ss[-1]['source_row'],discharge_start_test_time_s=times[0]-steps[0],discharge_end_test_time_s=times[-1],discharge_end_datetime=ss[-1]['datetime'],baseline_counter_Ah=None if prev is None else prev['discharge_counter_Ah'],end_counter_Ah=ss[-1]['discharge_counter_Ah'],counter_delta_candidate_Ah=qc,step_time_integral_candidate_Ah=qi,partial_integral_legacy_Ah=legacy_partial,capacity_Ah=qc if not flags else None,soh_nominal=qc/1.1 if not flags else None,end_voltage_V=ss[-1]['voltage_V'],charge_tail_voltage_V=None if not charge else charge[-1]['voltage_V'],charge_tail_current_A=None if not charge else charge[-1]['current_A'],first_interval_s=steps[0],current_median_A=-statistics.median(currents))
  result.append(base)
 return result
