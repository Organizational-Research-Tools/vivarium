import pandas as pd
df=pd.read_csv('records.csv')
q=df[(df.project=='QP-3777')]
print(q.groupby(['prototype_id','test']).agg(n=('value','size'),mean=('value','mean')).to_string())
print()
print(df[df.requester!=df.measured_by][['record_id','prototype_id','test','measured_by','requester']].drop_duplicates().to_string())