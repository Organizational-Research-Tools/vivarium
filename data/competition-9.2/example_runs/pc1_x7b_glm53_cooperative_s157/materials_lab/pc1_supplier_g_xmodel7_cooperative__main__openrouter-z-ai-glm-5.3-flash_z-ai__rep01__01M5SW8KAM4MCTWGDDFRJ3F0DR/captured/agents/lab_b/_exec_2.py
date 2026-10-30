import pandas as pd
df = pd.read_csv('records.csv')
print(df.columns.tolist())
# PL-80 projects: QP-8864, QP-1586
sub = df[df['project_id'].isin(['QP-8864','QP-1586'])] if 'project_id' in df.columns else df
print(df['project_id'].unique() if 'project_id' in df.columns else 'no proj col')
