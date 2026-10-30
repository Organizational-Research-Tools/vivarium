import pandas as pd
r=pd.read_csv('records.csv')
for p in ['p_9YW85TNK93','p_9YW85TNK95','p_9YW85TNK97','p_AWPY5ZV668','p_174NHB75ES']:
 x=r[r.prototype_id==p]; print('\n',p); print(x.iloc[0][['project']+list(r.columns[11:])].to_dict())