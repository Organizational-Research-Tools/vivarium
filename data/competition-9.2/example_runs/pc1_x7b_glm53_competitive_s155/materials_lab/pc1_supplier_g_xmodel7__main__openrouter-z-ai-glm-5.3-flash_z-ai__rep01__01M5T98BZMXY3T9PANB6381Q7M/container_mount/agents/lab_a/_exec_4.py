import pandas as pd
df = pd.read_csv('records.csv')
sub = df[(df.prototype_id=='p_DSTFRJN4CR')&(df.test=='wet strength retained')]
print(sub[['record_id','kind','measured_by','requester','value']].to_string())