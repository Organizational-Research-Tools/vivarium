import pandas as pd
x=pd.read_csv('records.csv')
y=x[(x.project=='QP-9219')&(x.instrument=='heat')&(x.kind=='qualification')&(x.prototype_id.str.startswith('p_YBRQHA8K'))]
print(','.join(y.record_id.tolist()))