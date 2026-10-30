import pandas as pd
df = pd.read_csv('records.csv')
ids=['p_5H6XYY0XDG','p_Z47MQWVTGK','p_Z47MQWVTGY']
print(df[df.prototype_id.isin(ids)][['prototype_id','project','test','kind','measured_by']].drop_duplicates().to_string())
print(df[(df.binder_system=='27X')].prototype_id.unique())
