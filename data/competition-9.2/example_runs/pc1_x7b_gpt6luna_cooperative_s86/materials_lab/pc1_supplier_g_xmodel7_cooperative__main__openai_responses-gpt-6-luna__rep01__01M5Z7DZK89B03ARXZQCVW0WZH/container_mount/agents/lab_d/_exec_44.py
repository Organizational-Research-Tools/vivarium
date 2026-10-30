d=pd.read_csv('records.csv'); d=d[d.kind=='qualification']; g=d.groupby(['project','prototype_id','instrument','test']).value.mean().unstack(['instrument','test']);
# collapse individual properties instrument may vary
m=d.groupby(['project','prototype_id','test']).value.mean().unstack(); counts=d.groupby(['project','prototype_id','test']).size().unstack(fill_value=0)
for proj in ['QP-9259','QP-9980','QP-9219','QP-3617','QP-6879']:
  z=m.loc[proj] if proj in m.index.get_level_values(0) else None
  if z is None: continue
  z=z.copy(); z['H']=z.get('seal hold temperature'); z['S']=z.get('edge crush resistance'); z['W']=z.get('wet strength retained')
  print('\n',proj)
  for pid,row in z.iterrows():
    h,s,w=row[['H','S','W']]
    if (pd.notna(h) and h>=78.25) or (pd.notna(s) and s>=7.19) or (pd.notna(w) and w>=79.2):
      vals = tuple(round(v,5) if pd.notna(v) else None for v in (h,s,w))
      print(pid, vals)
