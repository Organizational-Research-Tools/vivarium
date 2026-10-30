import pandas as pd
r=pd.read_csv('records.csv'); ps=['p_PKA1PMYYQB','p_PKA1PMYYQD','p_4YH1G6543W','p_4YH1G6543Y','p_4YH1G65440','p_4YH1G65442','p_4YH1G65444','p_4YH1G65446']
for p in ps:
 d=r[(r.prototype_id==p)&(r.test=='wet strength retained')]; print(p,round(d.value.mean(),4))