"""
诊断脚本：检查数据库连接、表数据、模块导入
执行：python diagnostic.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def check_database():
    """检查数据库连接和表数据"""
    print("=" * 60)
    print("1. 检查数据库连接和数据")
    print("=" * 60)
    
    try:
        from app.database import engine, AsyncSessionLocal
        from sqlalchemy import text
        
        async with AsyncSessionLocal() as db:
            # 检查各表数据量
            tables = [
                'risk_rule',
                'risk_assessment', 
                'risk_case',
                'risk_user_profile',
                'risk_event',
                'risk_feature',
                'account_info',
                'transaction_order'
            ]
            
            for table in tables:
                try:
                    result = await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.scalar()
                    print(f"✓ {table}: {count} 条记录")
                except Exception as e:
                    print(f"✗ {table}: 查询失败 - {e}")
                    
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def check_imports():
    """检查所有模块是否能正常导入"""
    print("\n" + "=" * 60)
    print("2. 检查模块导入")
    print("=" * 60)
    
    modules = [
        'app.models',
        'app.models_risk',
        'app.models_business',
        'app.schemas',
        'app.engine.rule',
        'app.engine.feature',
        'app.engine.decision',
        'app.service.case',
        'app.service.event',
        'app.agent.tools',
        'app.routers.profile',
        'app.routers.dashboard',
    ]
    
    all_ok = True
    for module_name in modules:
        try:
            __import__(module_name)
            print(f"✓ {module_name}")
        except Exception as e:
            print(f"✗ {module_name}: {e}")
            import traceback
            traceback.print_exc()
            all_ok = False
    
    return all_ok

async def check_risk_rules():
    """检查风险规则数据"""
    print("\n" + "=" * 60)
    print("3. 检查风险规则")
    print("=" * 60)
    
    try:
        from app.database import AsyncSessionLocal
        from app.models import RiskRule
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(RiskRule).where(RiskRule.is_enabled == 1)
            )
            rules = result.scalars().all()
            
            print(f"✓ 启用规则数: {len(rules)}")
            
            if len(rules) == 0:
                print("⚠ 警告: 没有启用的风险规则，需要先导入规则数据")
                print("  请执行: python scripts/gen_risk_data.py")
                return False
            
            # 显示前5条规则
            for i, rule in enumerate(rules[:5]):
                print(f"  {i+1}. [{rule.rule_category}] {rule.rule_name} (分值: {rule.risk_score})")
                
    except Exception as e:
        print(f"✗ 检查风险规则失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

async def main():
    print("\n" + "=" * 60)
    print("金融风控系统诊断工具")
    print("=" * 60 + "\n")
    
    # 1. 检查数据库
    db_ok = await check_database()
    
    # 2. 检查模块导入
    import_ok = check_imports()
    
    # 3. 检查风险规则
    rules_ok = await check_risk_rules() if db_ok else False
    
    # 总结
    print("\n" + "=" * 60)
    print("诊断结果")
    print("=" * 60)
    print(f"数据库连接: {'✓ 正常' if db_ok else '✗ 异常'}")
    print(f"模块导入: {'✓ 正常' if import_ok else '✗ 异常'}")
    print(f"风险规则: {'✓ 正常' if rules_ok else '✗ 异常'}")
    
    if db_ok and import_ok and rules_ok:
        print("\n✓ 系统状态正常，可以启动服务: python run_app.py")
    else:
        print("\n✗ 系统存在问题，请根据上述提示修复")
        if not db_ok:
            print("  - 检查 .env 文件中的数据库配置")
            print("  - 确保 MySQL 服务已启动")
        if not rules_ok and db_ok:
            print("  - 执行 python scripts/gen_risk_data.py 生成测试数据")

if __name__ == "__main__":
    asyncio.run(main())
