import pandas as pd
x=pd.read_csv('records.csv')
for prefix in ['p_8ATRDK3V3Z','p_9YW85TNK97','p_FF5QPYJ1FJ','p_FF5QPYJ1FM','p_FF5QPYJ1FP']:
 y=x[x.prototype_id.eq(prefix)]
 print(prefix, y.shape, y[['instrument','measured_by','value']].head(8).to_dict('records'))
