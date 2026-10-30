import pandas as pd
x=pd.read_csv('records.csv')
print(x.columns.tolist())
print(x.tail(3).to_string(index=False))
# Print all prototypes in target sets, any readings (these may be in latest records)
ids=['p_SVR5NZMYFG','p_SVR5NZMYFM','p_GRQC7S72K1','p_SVR5NZMYFE','p_GRQC7S72KF','p_S6067EX454','p_SVR5NZMYG6','p_3QBE171REF','p_6HZQR01SMB','p_DEH7S6TG4Y','p_DEH7S6TG50','p_DEH7S6TG5A','p_DEH7S6TG5C']
cols=[c for c in x.columns if c.lower().startswith('module') or c in ['project_id','prototype_id','kind','property','value','owner','instrument']]
print(x[x['prototype_id'].isin(ids)].to_string(index=False))