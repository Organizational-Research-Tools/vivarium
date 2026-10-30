import pandas as pd
df = pd.read_csv('records.csv')
for proj,pids in [('QP-1992',['p_S1J55G2ZV3','p_W7FY9708CG','p_E16M0W72XW']),
                  ('QP-5993',['p_HM0GYQGX10','p_CV61N6BF4M']),
                  ('QP-3777',['p_A2B8KB6SJC','p_6FKHJFZBEF','p_6FKHJFZBF1','p_ZD62ZAD3QM'])]:
    for pid in pids:
        sub = df[(df.project==proj)&(df.prototype_id==pid)]
        if len(sub):
            print(proj,pid,sub.recipe if 'recipe' in sub else '')
            print(sub.groupby('test').value.agg(['mean','max','count']).to_string())
            mods=[c for c in df.columns if c not in ('record_id','kind','project','prototype_id','instrument','test','specimen','value','unit','measured_by','requester')]
            print(sub[mods].dropna(axis=1,how='all').drop_duplicates().to_string())
            print()