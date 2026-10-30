import pandas as pd
df=pd.read_csv('records.csv')
mine=df[df.prototype_id=='p_N4RCVZ2GGA']
print(mine.to_string())