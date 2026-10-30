import pandas as pd
df = pd.read_csv('records.csv')
m = df[df['prototype_id'].astype(str).str.contains('VE|C0', regex=True)]
print(m.to_string()[:5000] if len(m) else 'none')
# also list new granted prototypes to me from lab_a
