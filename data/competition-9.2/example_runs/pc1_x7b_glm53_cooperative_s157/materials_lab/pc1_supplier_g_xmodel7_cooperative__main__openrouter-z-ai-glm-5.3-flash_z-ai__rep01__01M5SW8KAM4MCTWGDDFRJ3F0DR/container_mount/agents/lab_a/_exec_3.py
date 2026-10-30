import pandas as pd
df=pd.read_csv('records.csv')
print(df[['record_id','prototype_id','instrument','test','measured_by','requester']].drop_duplicates().head(30))
print(df['measured_by'].value_counts(), df['instrument'].value_counts(), df['test'].value_counts())