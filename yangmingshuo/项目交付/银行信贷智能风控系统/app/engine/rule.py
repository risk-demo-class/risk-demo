RULES=[
 ("R001","低信用评分","credit_score","<",550,30),("R002","KYC等级不足","kyc_level","<",2,35),
 ("R003","高负债率","debt_ratio",">",0.65,40),("R004","贷款金额超过月收入12倍","loan_income_multiple",">",12,35),
 ("R005","24小时登录失败过多","login_fail_24h",">=",5,35),("R006","设备数量异常","device_count",">",4,25),
 ("R007","大额转账","txn_amount",">",50000,45),("R008","夜间交易","night_transaction","==",1,20),
 ("R009","异地交易","cross_region","==",1,25),("R010","新账户申请信贷","account_age_days","<",30,30),
]
def match_rules(features):
    ops={"<":lambda a,b:a<b,">":lambda a,b:a>b,">=":lambda a,b:a>=b,"==":lambda a,b:a==b}
    return [{"rule_id":r,"name":n,"score":s} for r,n,k,o,v,s in RULES if k in features and ops[o](features[k],v)]

