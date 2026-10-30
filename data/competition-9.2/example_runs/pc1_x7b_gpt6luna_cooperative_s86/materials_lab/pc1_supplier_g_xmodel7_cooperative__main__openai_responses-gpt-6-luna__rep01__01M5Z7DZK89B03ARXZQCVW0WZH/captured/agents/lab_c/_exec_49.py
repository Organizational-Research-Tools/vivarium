import pandas as pd
r=pd.read_csv('records.csv'); p=r[r.prototype_id.eq('p_KBABVTJCX0')]; print(p[['record_id','instrument','test','specimen','value']].to_string(index=False))