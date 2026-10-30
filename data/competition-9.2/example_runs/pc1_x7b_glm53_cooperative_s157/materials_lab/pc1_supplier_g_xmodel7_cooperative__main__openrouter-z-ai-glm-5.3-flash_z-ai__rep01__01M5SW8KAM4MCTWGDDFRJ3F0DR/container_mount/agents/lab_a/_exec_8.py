import pandas as pd
df = pd.read_csv('records.csv')
q = df[(df.kind=='qualification') & df.project.isin(['QP-8864','QP-1586'])]
g = q.groupby(['project','prototype_id','test']).agg(n=('value','size'), mean=('value','mean'), who=('measured_by','first'))
for (p,pr),gr in g.groupby(level=[0,1]):
    m = {t:(n,round(v,3)) for (pp,pt,t),(n,v) in gr.mean(level=[2]).iterrows()} if False else None
    d = gr.reset_index()
    print(p, pr, dict(zip(d.test, zip(d.n, d['mean'].round(3)))), d.who.iloc[0])