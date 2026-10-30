import pandas as pd
x=pd.read_csv('records.csv'); g=x[x.base_sheet=='H8Z']; print(g.groupby(['prototype_id','instrument']).agg(n=('record_id','size'),mean=('value','mean')).to_string()); print('\nIDs by instrument');
for ins in ['heat','strength','water']:
 z=g[(g.instrument==ins)&(g.kind=='qualification')]; print(ins,list(z.record_id),z.value.mean())