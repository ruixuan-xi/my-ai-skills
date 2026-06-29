# -*- coding: utf-8 -*-
"""
Generate a Mermaid flowchart from JSON config steps.
Outputs: .mmd source file, .html interactive editor, and .png image.

Usage:
    python gen_flowchart.py <config.json> [<output_dir>]
"""
import os
import sys
import json
import base64


def steps_to_mermaid(steps, title="业务流程图"):
    """
    Convert steps list to Mermaid flowchart code.
    
    Steps are assumed to be sequential with optional branches.
    For now, generates a simple top-down flowchart.
    
    Args:
        steps: List of step dicts with 'name' and optionally 'type' ('start', 'end', 'decision', 'process')
        title: Flowchart title
    
    Returns:
        Mermaid flowchart code string
    """
    lines = [
        "---",
        f"title: {title}",
        "---",
        "flowchart TD",
        "    %% Style definitions",
        "    classDef startEnd fill:#E1D5E7,stroke:#9673A6,stroke-width:2px,color:#333;",
        "    classDef process fill:#DAE8FC,stroke:#6C8EBF,stroke-width:1px,color:#333;",
        "    classDef decision fill:#FFF2CC,stroke:#D6B656,stroke-width:1px,color:#333;",
        "    classDef action fill:#F8CECC,stroke:#B85450,stroke-width:1px,color:#333;",
    ]
    
    if not steps:
        lines.append("    A[暂无流程步骤]")
        return "\n".join(lines)
    
    # Generate nodes
    node_map = {}
    for i, step in enumerate(steps):
        node_id = f"S{i+1}"
        node_map[i] = node_id
        
        name = step.get('name', f'步骤{i+1}').replace('[', '【').replace(']', '】')
        step_type = step.get('type', 'process')
        
        if step_type == 'start':
            lines.append(f"    {node_id}([{name}]):::startEnd")
        elif step_type == 'end':
            lines.append(f"    {node_id}([{name}]):::startEnd")
        elif step_type == 'decision':
            lines.append(f"    {node_id}{{{name}}}:::decision")
        elif step_type == 'action':
            lines.append(f"    {node_id}[{name}]:::action")
        else:
            lines.append(f"    {node_id}[{name}]:::process")
    
    # Generate connections
    lines.append("")
    lines.append("    %% Connections")
    for i in range(len(steps) - 1):
        curr_id = node_map[i]
        next_id = node_map[i + 1]
        lines.append(f"    {curr_id} --> {next_id}")
    
    # Handle branches if specified
    for i, step in enumerate(steps):
        if 'yes' in step or 'no' in step:
            curr_id = node_map[i]
            if 'yes' in step and step['yes'] is not None:
                target_idx = step['yes']
                if 0 <= target_idx < len(steps):
                    lines.append(f"    {curr_id} -->|是| {node_map[target_idx]}")
            if 'no' in step and step['no'] is not None:
                target_idx = step['no']
                if 0 <= target_idx < len(steps):
                    lines.append(f"    {curr_id} -->|否| {node_map[target_idx]}")
    
    return "\n".join(lines)


def create_html_editor(mermaid_code, title="流程图编辑器"):
    """Create a self-contained HTML file with Mermaid editor."""
    html_template = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{title}}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            display: flex;
            gap: 20px;
            height: calc(100vh - 40px);
        }}
        .panel {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .editor-panel {{ flex: 1; min-width: 400px; }}
        .preview-panel {{ flex: 1.5; min-width: 500px; }}
        .panel-header {{
            background: #333;
            color: white;
            padding: 12px 16px;
            font-weight: 600;
            font-size: 14px;
        }}
        .panel-body {{
            flex: 1;
            overflow: auto;
            padding: 0;
        }}
        textarea {{
            width: 100%;
            height: 100%;
            border: none;
            padding: 16px;
            font-family: "Consolas", "Monaco", "Courier New", monospace;
            font-size: 13px;
            line-height: 1.6;
            resize: none;
            outline: none;
        }}
        #preview {{
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: flex-start;
        }}
        .mermaid {{
            min-width: 200px;
        }}
        .tips {{
            background: #FFF3CD;
            border-left: 4px solid #FFC107;
            padding: 12px 16px;
            margin: 16px;
            border-radius: 4px;
            font-size: 13px;
            color: #856404;
        }}
        .tips h4 {{ margin: 0 0 8px 0; }}
        .tips ul {{ margin: 0; padding-left: 18px; }}
        .tips li {{ margin: 4px 0; }}
        .actions {{
            padding: 12px 16px;
            background: #f8f9fa;
            border-top: 1px solid #e9ecef;
            display: flex;
            gap: 8px;
        }}
        button {{
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
        }}
        .btn-primary {{ background: #007BFF; color: white; }}
        .btn-primary:hover {{ background: #0056b3; }}
        .btn-secondary {{ background: #6C757D; color: white; }}
        .btn-secondary:hover {{ background: #545b62; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="panel editor-panel">
            <div class="panel-header">📝 Mermaid 代码编辑器</div>
            <div class="panel-body" style="display: flex; flex-direction: column;">
                <textarea id="mermaid-code" spellcheck="false">{{mermaid_code}}</textarea>
                <div class="tips">
                    <h4>💡 快速提示</h4>
                    <ul>
                        <li><code>([文本])</code> = 开始/结束（椭圆）</li>
                        <li><code>[文本]</code> = 处理步骤（矩形）</li>
                        <li><code>{{{{文本}}}}</code> = 判断（菱形）</li>
                        <li><code>--&gt;|标签|</code> = 带标签的连接线</li>
                    </ul>
                </div>
                <div class="actions">
                    <button class="btn-primary" onclick="renderChart()">🔄 重新渲染</button>
                    <button class="btn-secondary" onclick="downloadCode()">💾 下载代码</button>
                    <button class="btn-secondary" onclick="downloadPNG()">🖼️ 下载PNG</button>
                </div>
            </div>
        </div>
        <div class="panel preview-panel">
            <div class="panel-header">👁️ 流程图预览</div>
            <div class="panel-body" id="preview"></div>
        </div>
    </div>

    <script>
        mermaid.initialize({{
            startOnLoad: false,
            theme: 'default',
            flowchart: {{
                useMaxWidth: true,
                htmlLabels: true,
                curve: 'basis'
            }}
        }});

        const codeEditor = document.getElementById('mermaid-code');
        const previewContainer = document.getElementById('preview');

        async function renderChart() {{
            const code = codeEditor.value;
            previewContainer.innerHTML = '<div class="mermaid">' + code + '</div>';
            try {{
                await mermaid.run({{ querySelector: '.mermaid' }});
            }} catch (e) {{
                previewContainer.innerHTML = '<p style="color:red;">渲染错误: ' + e.message + '</p>';
            }}
        }}

        function downloadCode() {{
            const code = codeEditor.value;
            const blob = new Blob([code], {{ type: 'text/plain' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'flowchart.mmd';
            a.click();
            URL.revokeObjectURL(url);
        }}

        async function downloadPNG() {{
            const svg = previewContainer.querySelector('svg');
            if (!svg) {{
                alert('请先渲染流程图');
                return;
            }}
            
            const svgData = new XMLSerializer().serializeToString(svg);
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');
            const img = new Image();
            
            const svgBlob = new Blob([svgData], {{ type: 'image/svg+xml;charset=utf-8' }});
            const url = URL.createObjectURL(svgBlob);
            
            img.onload = function() {{
                canvas.width = img.width * 2;
                canvas.height = img.height * 2;
                ctx.scale(2, 2);
                ctx.drawImage(img, 0, 0);
                URL.revokeObjectURL(url);
                
                const pngUrl = canvas.toDataURL('image/png');
                const a = document.createElement('a');
                a.href = pngUrl;
                a.download = 'flowchart.png';
                a.click();
            }};
            img.src = url;
        }}

        // Initial render
        renderChart();

        // Auto-render on Ctrl+Enter
        codeEditor.addEventListener('keydown', function(e) {{
            if (e.ctrlKey && e.key === 'Enter') {{
                renderChart();
            }}
        }});
    </script>
</body>
</html>'''
    # f-string 已将 {{title}} → {title}, {{mermaid_code}} → {mermaid_code}
    return html_template.replace('{title}', title).replace('{mermaid_code}', mermaid_code)


def generate_flowchart(config, output_dir=None):
    """
    Generate flowchart files from config.
    
    Args:
        config: Dict with 'title', 'steps' (optional 'flowchart_title')
        output_dir: Output directory (default: current directory)
    
    Returns:
        Dict with paths to generated files
    """
    if output_dir is None:
        output_dir = os.getcwd()
    
    os.makedirs(output_dir, exist_ok=True)
    
    title = config.get('flowchart_title', config.get('title', '业务流程图'))
    steps = config.get('steps', [])
    
    # Add start and end nodes if not present
    processed_steps = []
    if not any(s.get('type') == 'start' for s in steps):
        processed_steps.append({'name': '开始', 'type': 'start'})
    
    for s in steps:
        processed_steps.append(s)
    
    if not any(s.get('type') == 'end' for s in steps):
        processed_steps.append({'name': '结束', 'type': 'end'})
    
    # Generate Mermaid code
    mermaid_code = steps_to_mermaid(processed_steps, title)
    
    # Save .mmd file
    base_name = config.get('output_path', 'flowchart').replace('.docx', '').replace('.html', '')
    base_name = os.path.basename(base_name)
    mmd_path = os.path.join(output_dir, f"{base_name}_flowchart.mmd")
    with open(mmd_path, 'w', encoding='utf-8') as f:
        f.write(mermaid_code)
    
    # Save .html file
    html_path = os.path.join(output_dir, f"{base_name}_flowchart.html")
    html_content = create_html_editor(mermaid_code, title)
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Flowchart generated:")
    print(f"  - Mermaid source: {mmd_path}")
    print(f"  - HTML editor:    {html_path}")
    
    return {
        'mmd_path': mmd_path,
        'html_path': html_path,
        'mermaid_code': mermaid_code
    }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python gen_flowchart.py <config.json> [<output_dir>]")
        sys.exit(1)
    
    config_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    generate_flowchart(config, output_dir)
