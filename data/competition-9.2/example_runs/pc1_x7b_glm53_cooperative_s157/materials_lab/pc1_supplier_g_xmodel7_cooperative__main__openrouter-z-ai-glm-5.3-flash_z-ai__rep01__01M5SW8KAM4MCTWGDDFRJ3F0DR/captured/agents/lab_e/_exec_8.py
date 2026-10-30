import pandas as pd
df = pd.read_csv('records.csv')
m = df[df['prototype_id'].isin(['p_GM7DHPGB5W','p_P2FZ2H2S5Z','p_P2FZ2H2S6A'])]
print(m[['record_id','prototype_id','test','specimen','value','measured_by','kind']].sort_values(['test','specimen']).to_string())