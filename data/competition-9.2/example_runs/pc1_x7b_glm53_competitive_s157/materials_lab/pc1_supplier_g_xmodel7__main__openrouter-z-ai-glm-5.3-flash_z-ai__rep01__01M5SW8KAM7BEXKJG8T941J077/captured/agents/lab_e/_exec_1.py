import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
rows = df[df.prototype_id.isin(['p_W39ZPSCGQ3','p_MTSR9DF2A5','p_5H6XYY0XDG'])]
print(rows.drop_duplicates(subset=['prototype_id']).to_string())