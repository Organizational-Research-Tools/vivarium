import pandas as pd
x=pd.read_csv('records.csv')
ps=['p_SNNF91F2XB','p_1XF9VFBVYF','p_SNNF91F2XD','p_S5W8G1Y5NY','p_D7M43Y22PV']
print(x[x.prototype_id.isin(ps)].groupby(['prototype_id','test','kind']).value.agg(['count','mean']).to_string())