"""
ASCII转图片工具脚本
将文档切分流程的ASCII图转换为图片格式
"""

from PIL import Image, ImageDraw, ImageFont
import textwrap

# ASCII流程图内容
ascii_diagram = """
文档切分节点流程图 (NodeDocumentSplit)
================================================================================

                    输入: ImportGraphState
                    ├── file_title: 文件标题
                    └── md_content: Markdown内容
                            │
                            ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    process(state) 主流程                                │
└───────────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   ┌────────┐        ┌──────────┐        ┌────────────┐
   │ Step 1 │        │ Step 2   │        │ Step 4     │
   │ 输入校验│  ──→  │ 标题切分  │  ──→  │ 精细化处理  │
   └────────┘        └──────────┘        └────────────┘
        │                   │                   │
        │                   ▼                   │
        │          ┌────────────────┐           │
        │          │ 识别MD标题      │           │
        │          │ 1-6级标题模式    │           │
        │          │ 跳过代码块     │           │
        │          └────────────────┘           │
        │                   │                   │
        │                   ▼                   │
        │          ┌────────────────┐           │
        │          │ 按标题分章节    │           │
        │          └────────────────┘           │
        │                   │                   ▼
        │                   │          ┌─────────────────────┐
        │                   │          │ 长切短合策略         │
        │                   │          └─────────────────────┘
        │                   │                   │
        │                   │      ┌────────────┴────────────┐
        │                   │      │                         │
        │                   │      ▼                         ▼
        │                   │ ┌──────────┐            ┌──────────┐
        │                   │ │切分超长  │            │合并过短  │
        │                   │ │章节      │            │章节      │
        │                   │ └──────────┘            └──────────┘
        │                   │      │                         │
        │                   │      ▼                         ▼
        │                   │ ┌──────────┐            ┌──────────┐
        │                   │ │递归文本  │            │同父标题  │
        │                   │ │切分      │            │合并策略  │
        │                   │ └──────────┘            └──────────┘
        │                   │      │                         │
        └───────────────────┴──────┴─────────────────────────┘
                            │
                            ▼
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   ┌────────┐        ┌──────────┐        ┌────────────┐
   │ Step 5 │        │ Step 6   │        │  返回结果   │
   │ 统计信息│  ──→  │ 备份JSON │  ──→  │ chunks列表 │
   └────────┘        └──────────┘        └────────────┘
                            │
                            ▼
                    输出: {"chunks": sections}
                    ├── file_title: 文件名
                    ├── title: 章节标题  
                    ├── content: 章节内容
                    ├── parent_title: 父标题
                    └── part: 分段序号
"""


def create_ascii_image(ascii_text, output_path="document_split_flow.png", font_size=12):
    """
    将ASCII文本转换为图片
    
    Args:
        ascii_text: ASCII文本内容
        output_path: 输出图片路径
        font_size: 字体大小
    """
    
    # 计算图片尺寸
    lines = ascii_text.split('\n')
    max_width = max(len(line) for line in lines) if lines else 100
    total_height = len(lines)
    
    # 设置字符大小和图片尺寸
    char_width = font_size * 0.6  # 字符宽度比例
    char_height = font_size * 1.2  # 字符高度比例
    
    img_width = int(max_width * char_width) + 100
    img_height = int(total_height * char_height) + 100
    
    # 创建图片
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    # 尝试加载中文字体
    try:
        # Windows中文字体路径
        font_paths = [
            "C:/Windows/Fonts/simsun.ttc",  # 宋体
            "C:/Windows/Fonts/msyh.ttc",    # 微软雅黑
            "C:/Windows/Fonts/simhei.ttf",  # 黑体
        ]
        
        font = None
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except:
                continue
        
        if font is None:
            font = ImageFont.load_default()
            
    except Exception as e:
        print(f"字体加载失败，使用默认字体: {e}")
        font = ImageFont.load_default()
    
    # 绘制文本
    y_offset = 50
    for line in lines:
        draw.text((50, y_offset), line, font=font, fill='black')
        y_offset += int(char_height)
    
    # 保存图片
    img.save(output_path)
    print(f"图片已保存到: {output_path}")
    return output_path


def create_detailed_flowchart():
    """
    创建更详细的流程图，使用图形化元素
    """
    
    # 创建更大的画布
    img_width, img_height = 1200, 1600
    img = Image.new('RGB', (img_width, img_height), color='white')
    draw = ImageDraw.Draw(img)
    
    # 尝试加载字体
    try:
        font_paths = [
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simsun.ttc",
        ]
        
        title_font = None
        text_font = None
        
        for font_path in font_paths:
            try:
                title_font = ImageFont.truetype(font_path, 20)
                text_font = ImageFont.truetype(font_path, 14)
                break
            except:
                continue
        
        if title_font is None:
            title_font = ImageFont.load_default()
            text_font = ImageFont.load_default()
            
    except Exception as e:
        print(f"字体加载失败: {e}")
        title_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
    
    # 定义颜色
    colors = {
        'title': '#1f77b4',
        'box': '#aec7e8',
        'arrow': '#2ca02c',
        'text': '#333333',
        'background': '#ffffff'
    }
    
    # 绘制标题
    title = "文档切分节点流程图 (NodeDocumentSplit)"
    draw.text((img_width//2 - 150, 20), title, font=title_font, fill=colors['title'])
    
    # 定义节点位置
    nodes = [
        # (x, y, width, height, text, color)
        (400, 80, 400, 60, "输入: ImportGraphState", '#ffbb78'),
        (400, 180, 400, 50, "process(state) 主流程", '#98df8a'),
        (200, 280, 150, 60, "Step 1\n输入校验", '#aec7e8'),
        (525, 280, 150, 60, "Step 2\n标题切分", '#aec7e8'),
        (850, 280, 150, 60, "Step 4\n精细化处理", '#aec7e8'),
        (400, 400, 250, 80, "识别MD标题\n1-6级标题模式\n跳过代码块", '#c5b0d5'),
        (400, 520, 250, 60, "按标题分章节", '#c5b0d5'),
        (300, 620, 200, 60, "长切短合策略", '#ff9896'),
        (200, 720, 150, 60, "切分超长章节", '#f7b6d2'),
        (450, 720, 150, 60, "合并过短章节", '#f7b6d2'),
        (200, 820, 150, 60, "递归文本切分", '#dbdb8d'),
        (450, 820, 150, 60, "同父标题合并", '#dbdb8d'),
        (200, 940, 150, 60, "Step 5\n统计信息", '#aec7e8'),
        (525, 940, 150, 60, "Step 6\n备份JSON", '#aec7e8'),
        (850, 940, 150, 60, "返回结果", '#9edae5'),
        (400, 1040, 400, 100, "输出: chunks列表\n├── file_title: 文件名\n├── title: 章节标题\n├── content: 章节内容\n├── parent_title: 父标题\n└── part: 分段序号", '#c7c7c7'),
    ]
    
    # 绘制节点
    for x, y, width, height, text, color in nodes:
        # 绘制矩形
        draw.rectangle([x, y, x+width, y+height], fill=color, outline='black', width=2)
        
        # 绘制文本（处理多行文本）
        lines = text.split('\n')
        text_y = y + 10
        for line in lines:
            draw.text((x + 10, text_y), line, font=text_font, fill=colors['text'])
            text_y += 20
    
    # 绘制箭头函数
    def draw_arrow(x1, y1, x2, y2):
        """绘制箭头"""
        draw.line([x1, y1, x2, y2], fill=colors['arrow'], width=3)
        # 箭头头部
        arrow_size = 10
        if x1 == x2:  # 垂直线
            if y1 < y2:  # 向下
                draw.polygon([(x2-arrow_size, y2-arrow_size), (x2+arrow_size, y2-arrow_size), (x2, y2)], fill=colors['arrow'])
            else:  # 向上
                draw.polygon([(x2-arrow_size, y2+arrow_size), (x2+arrow_size, y2+arrow_size), (x2, y2)], fill=colors['arrow'])
        else:  # 水平线或斜线
            if x1 < x2:  # 向右
                draw.polygon([(x2-arrow_size, y2-arrow_size), (x2-arrow_size, y2+arrow_size), (x2, y2)], fill=colors['arrow'])
            else:  # 向左
                draw.polygon([(x2+arrow_size, y2-arrow_size), (x2+arrow_size, y2+arrow_size), (x2, y2)], fill=colors['arrow'])
    
    # 绘制连接箭头
    arrows = [
        # 主流程垂直连接
        (600, 140, 600, 180),  # 输入到主流程
        (600, 230, 600, 280),  # 主流程到步骤1-2-4
        (275, 340, 275, 400, 600, 400, 600, 520),  # 步骤1到标题识别
        (600, 340, 600, 400),  # 步骤2到标题识别
        (925, 340, 925, 520, 600, 520),  # 步骤4到标题识别
        (525, 580, 525, 620),  # 标题分章节到长切短合
        (400, 680, 400, 720),  # 长切短合到切分超长
        (525, 680, 525, 720),  # 长切短合到合并过短
        (275, 780, 275, 820),  # 切分超长到递归切分
        (525, 780, 525, 820),  # 合并过短到同父标题
        (275, 880, 275, 940),  # 递归切分到统计信息
        (525, 880, 525, 940),  # 同父标题到备份JSON
        (275, 1000, 275, 1040, 400, 1040),  # 统计信息到输出
        (600, 1000, 600, 1040),  # 备份JSON到输出
    ]
    
    for arrow in arrows:
        if len(arrow) == 4:  # 简单箭头
            draw_arrow(*arrow)
        else:  # 折线箭头
            for i in range(0, len(arrow)-2, 2):
                draw_arrow(arrow[i], arrow[i+1], arrow[i+2], arrow[i+3])
    
    # 保存图片
    output_path = "document_split_flow_detailed.png"
    img.save(output_path)
    print(f"详细流程图已保存到: {output_path}")
    return output_path


if __name__ == "__main__":
    print("正在生成ASCII流程图...")
    
    # 生成简单的ASCII转图片
    create_ascii_image(ascii_diagram, "document_split_ascii.png")
    
    print("\n正在生成详细流程图...")
    # 生成详细的图形化流程图
    create_detailed_flowchart()
    
    print("\n图片生成完成！")