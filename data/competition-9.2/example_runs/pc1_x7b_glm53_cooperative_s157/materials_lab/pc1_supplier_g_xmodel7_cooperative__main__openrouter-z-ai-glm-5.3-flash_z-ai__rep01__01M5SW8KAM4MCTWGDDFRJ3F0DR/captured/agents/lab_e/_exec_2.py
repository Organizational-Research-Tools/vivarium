df = pd.read_csv('records.csv')
print(df.columns.tolist())
m = df[df['prototype_id'].astype(str).str.contains('VE|C0|C10', regex=True)]
print(m.to_string()[:4000] if len(m) else 'none')