import pandas as pd
df = pd.read_csv('records.csv')
m = df[df['prototype_id'].isin(['p_JP4D3NK6YX','p_JP4D3NK6Z8'])]
print(m[['record_id','prototype_id','instrument','test','specimen','value','measured_by']].sort_values(['test','specimen']).to_string())