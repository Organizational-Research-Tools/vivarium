import pandas as pd
df=pd.read_csv('records.csv')
# water on lab_a's 48 QP-6820 variants: any granted prototypes with water exploratory?
w=df[(df.project=='QP-6820')&(df.test=='wet strength retained')&(df.kind=='exploratory')]
g=w.groupby('prototype_id').value.agg(['mean','count']).sort_values('mean',ascending=False)
print(g.head(15))
# strength on QP-2236 p_BKPPQQPHJF and QP-1586
for pid in ['p_BKPPQQPHJF','p_55NSKA6RFT']:
    g2=df[(df.prototype_id==pid)&(df.kind=='exploratory')]
    print(pid, g2.groupby('test').value.agg(['mean','count']))
