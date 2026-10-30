import pandas as pd
x=pd.read_csv('records.csv'); q=x[x.kind.eq('qualification')]
g=q.groupby(['prototype_id','project','test']).agg(n=('value','count'),mean=('value','mean'))
w=g.reset_index().pivot(index=['prototype_id','project'],columns='test',values=['n','mean']); w.columns=['_'.join(str(z) for z in c) for c in w.columns]
H='mean_seal hold temperature'; S='mean_edge crush resistance'; W='mean_wet strength retained'
# qualifying heat+strength, water panel doesn't pass/missing
c=w[(w['n_seal hold temperature']>=6)&(w[H]>=78.25)&(w['n_edge crush resistance']>=6)&(w[S]>=7.19)&((w.get(W,pd.Series(index=w.index,dtype=float))<79.2)|(w.get('n_wet strength retained',pd.Series(index=w.index,dtype=float))<6))]
print(len(c)); print(c.sort_values(S,ascending=False).to_string(max_rows=100))