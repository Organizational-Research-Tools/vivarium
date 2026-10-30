import pandas as pd
x=pd.read_csv('records.csv');
for p in ['p_FF5QPYJ1FJ','p_FF5QPYJ1FM','p_FF5QPYJ1FP','p_EZR46XFBAD','p_EZR46XFBAH','p_ZDYAYEX9AC']:
 z=x[x.prototype_id==p]; print(p,[(t,round(g.value.mean(),5)) for t,g in z.groupby('test')])