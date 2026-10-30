import pandas as pd
x=pd.read_csv('records.csv'); q=x[(x.project.isin(['QP-6879','QP-3617','QP-9273'])) & (x.kind=='exploratory')];
for (pr,pid,t),z in q.groupby(['project','prototype_id','test']):
 print(pr,pid,t,len(z),round(z.value.mean(),5),z.measured_by.iloc[0])