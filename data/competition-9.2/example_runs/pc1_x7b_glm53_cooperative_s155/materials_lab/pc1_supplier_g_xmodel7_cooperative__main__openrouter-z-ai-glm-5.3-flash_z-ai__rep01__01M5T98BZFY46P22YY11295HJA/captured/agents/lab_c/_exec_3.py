import pandas as pd
df=pd.read_csv('records.csv')
cols=df.columns[11:23].tolist()
prot=df.drop_duplicates('prototype_id')[['project','prototype_id','measured_by']+cols]
print(prot.to_string())