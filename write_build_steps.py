"""
渐进构建数据写入脚本
1. 备份现有表到 _backup_v5
2. 创建 quest_build_steps 表
3. 事务写入 999 个 sequence 的 3623 个步骤
"""
import json
import pymysql
import uuid
from datetime import datetime

# 数据库配置
DB_CONFIG = {
    'host': 'gateway01.eu-central-1.prod.aws.tidbcloud.com',
    'port': 4000,
    'user': '3YfVDvhdkmKchdq.root',
    'password': 'Xwfvl1gRh6KYeqCG',
    'database': 'russian_learning',
    'ssl': {'ssl': {}}
}

# 加载渐进构建数据
with open(r'C:\Users\张宏飞\russian-learning\progressive_999sentences_result_v2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

sequences = data['sequences']
print(f'加载数据: {len(sequences)} 个 sequence')

# 统计总步骤数
total_steps = sum(len(seq['steps']) for seq in sequences)
print(f'总步骤数: {total_steps}')

# 连接数据库
conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

try:
    # ============================================
    # 第1步：备份现有表
    # ============================================
    print('\n' + '='*60)
    print('第1步：备份现有表到 _backup_v5')
    print('='*60)
    
    tables_to_backup = ['quest_statements', 'quest_words', 'quest_acceptable_answers']
    
    for table in tables_to_backup:
        backup_table = f'{table}_backup_v5'
        
        # 检查备份表是否已存在
        cursor.execute(f"SHOW TABLES LIKE '{backup_table}'")
        if cursor.fetchone():
            print(f'  ⚠️ {backup_table} 已存在，跳过创建')
        else:
            # 创建备份表（结构+数据）
            print(f'  备份 {table} -> {backup_table}...')
            cursor.execute(f"CREATE TABLE {backup_table} LIKE {table}")
            cursor.execute(f"INSERT INTO {backup_table} SELECT * FROM {table}")
            conn.commit()
        
        # 统计记录数
        cursor.execute(f"SELECT COUNT(*) FROM {backup_table}")
        count = cursor.fetchone()[0]
        print(f'  ✅ {backup_table}: {count} 条记录')
    
    # ============================================
    # 第2步：创建 quest_build_steps 表
    # ============================================
    print('\n' + '='*60)
    print('第2步：创建 quest_build_steps 表')
    print('='*60)
    
    cursor.execute("SHOW TABLES LIKE 'quest_build_steps'")
    if cursor.fetchone():
        print('  ⚠️ quest_build_steps 已存在，先清空')
        cursor.execute("TRUNCATE TABLE quest_build_steps")
    else:
        print('  创建 quest_build_steps 表...')
        cursor.execute("""
            CREATE TABLE quest_build_steps (
                id VARCHAR(36) PRIMARY KEY,
                sequence_id VARCHAR(36) NOT NULL,
                step_order INT NOT NULL,
                target_sentence TEXT NOT NULL,
                chinese TEXT,
                action VARCHAR(50),
                new_element VARCHAR(255),
                full_sentence TEXT,
                full_chinese TEXT,
                is_complete TINYINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_sequence (sequence_id),
                INDEX idx_sequence_order (sequence_id, step_order)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        print('  ✅ quest_build_steps 表创建成功')
    
    conn.commit()
    
    # ============================================
    # 第3步：事务写入数据
    # ============================================
    print('\n' + '='*60)
    print('第3步：事务写入渐进构建数据')
    print('='*60)
    
    inserted = 0
    errors = 0
    
    # 开始事务
    cursor.execute("START TRANSACTION")
    
    try:
        for seq_idx, seq in enumerate(sequences):
            sequence_id = seq['id']
            full_russian = seq['full_russian']
            full_chinese = seq['full_chinese']
            
            for step in seq['steps']:
                step_id = str(uuid.uuid4())
                step_order = step['step']
                target_sentence = step['russian']
                chinese = step.get('chinese', '')
                action = step.get('action', 'build')
                new_element = step.get('new_element', '')
                is_complete = 1 if step.get('is_complete', False) else 0
                
                cursor.execute("""
                    INSERT INTO quest_build_steps 
                    (id, sequence_id, step_order, target_sentence, chinese, 
                     action, new_element, full_sentence, full_chinese, is_complete)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (step_id, sequence_id, step_order, target_sentence, chinese,
                      action, new_element, full_russian, full_chinese, is_complete))
                inserted += 1
            
            if (seq_idx + 1) % 100 == 0:
                print(f'  已处理 {seq_idx + 1}/{len(sequences)} 个 sequence，写入 {inserted} 条步骤')
        
        # 提交事务
        conn.commit()
        print(f'\n  ✅ 事务提交成功！共写入 {inserted} 条步骤')
        
    except Exception as e:
        # 回滚事务
        conn.rollback()
        errors += 1
        print(f'\n  ❌ 事务失败，已回滚: {e}')
        raise
    
    # ============================================
    # 第4步：写入后完整性验证
    # ============================================
    print('\n' + '='*60)
    print('第4步：写入后完整性验证')
    print('='*60)
    
    # 总记录数
    cursor.execute("SELECT COUNT(*) FROM quest_build_steps")
    total = cursor.fetchone()[0]
    print(f'  quest_build_steps 总记录数: {total}')
    
    # 总 sequence 数
    cursor.execute("SELECT COUNT(DISTINCT sequence_id) FROM quest_build_steps")
    total_seq = cursor.fetchone()[0]
    print(f'  总 sequence 数: {total_seq}')
    
    # sequence_id 为空异常数
    cursor.execute("SELECT COUNT(*) FROM quest_build_steps WHERE sequence_id IS NULL OR sequence_id = ''")
    null_seq = cursor.fetchone()[0]
    print(f'  sequence_id 为空异常数: {null_seq} (应为0)')
    
    # step_order 重复异常数
    cursor.execute("""
        SELECT COUNT(*) FROM (
            SELECT sequence_id, step_order, COUNT(*) as cnt
            FROM quest_build_steps
            GROUP BY sequence_id, step_order
            HAVING cnt > 1
        ) as duplicates
    """)
    duplicate_order = cursor.fetchone()[0]
    print(f'  step_order 重复异常数: {duplicate_order} (应为0)')
    
    # 随机抽3个 sequence 输出完整数据
    print(f'\n  随机抽3个 sequence 完整数据:')
    print('  ' + '-'*60)
    
    cursor.execute("""
        SELECT DISTINCT sequence_id FROM quest_build_steps 
        ORDER BY RAND() LIMIT 3
    """)
    sample_seqs = cursor.fetchall()
    
    for seq_id_tuple in sample_seqs:
        seq_id = seq_id_tuple[0]
        cursor.execute("""
            SELECT step_order, target_sentence, chinese, action, is_complete
            FROM quest_build_steps
            WHERE sequence_id = %s
            ORDER BY step_order
        """, (seq_id,))
        steps = cursor.fetchall()
        
        # 获取完整句信息
        cursor.execute("""
            SELECT full_sentence, full_chinese FROM quest_build_steps
            WHERE sequence_id = %s AND is_complete = 1 LIMIT 1
        """, (seq_id,))
        full_info = cursor.fetchone()
        
        print(f'\n  sequence_id: {seq_id}')
        if full_info:
            print(f'  完整句: {full_info[0]} → {full_info[1]}')
        print(f'  步骤数: {len(steps)}')
        for step in steps:
            marker = '✅' if step[4] else '  '
            print(f'    {marker} step{step[0]:2d}: {step[1]:30s} → {step[2]} (action: {step[3]})')
    
    print('\n' + '='*60)
    print('✅ 写入完成！')
    print('='*60)
    print(f'  总记录数: {total}')
    print(f'  总 sequence 数: {total_seq}')
    print(f'  sequence_id 为空: {null_seq}')
    print(f'  step_order 重复: {duplicate_order}')
    print(f'  备份表: quest_statements_backup_v5, quest_words_backup_v5, quest_acceptable_answers_backup_v5')
    
except Exception as e:
    print(f'\n❌ 执行失败: {e}')
    import traceback
    traceback.print_exc()
finally:
    cursor.close()
    conn.close()
