import pandas as pd
x=pd.read_csv('records.csv')
ids=['p_1R7D8ZYK1G','p_1R7D8ZYK1J','p_1R7D8ZYK1M','p_FZR98ZZADR']
y=x[x.prototype_id.isin(ids)]
print(y.groupby(['prototype_id','test','kind','measured_by']).value.agg(['count','mean']).to_string())