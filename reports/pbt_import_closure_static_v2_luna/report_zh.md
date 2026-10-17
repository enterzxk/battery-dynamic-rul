# PBT 固定源码导入闭包与执行阶段静态审计 v2

状态：STATIC_AST_PHASE_CLASSIFIED_IMPORT_CLOSURE_ONLY。这是 create-only v2；v1 与现有 proposal/contract 均未修改。proposal 候选仍 inactive。审计未作模型 GO/STOP 判断。

## 固定范围与结果

入口 repos/pinned/PBT_122077bc5435bb0ba5406f2b112fa96903a08c6a/models/PBT.py SHA-256 为 171646ca4821eeac74b61f2a23b5f2381179a571d890994866dd0e3acc8655a，与 proposal 一致。指定 Python /home/yndx/miniconda3/envs/a40_env/bin/python 仅运行本目录静态脚本。结果递归覆盖 15 个仓库内可定位 Python 文件、24 条项目导入边；逐文件 SHA、导入行号/模块名/符号/解析状态/上下文、执行阶段记录见 audit.json。脚本为 audit_import_closure.py。

AST 执行阶段现在分为：

- module_body_execution：模块体语句实际执行阶段；入口 PBT.py 第33行的 transformers.logging.set_verbosity_error() 是确认的进程级日志配置副作用。
- definition_time：模块/类定义过程中求值的类基类、装饰器、函数或方法默认参数、注解、返回注解等。调用表达式记录为求值表达式，不代表模型构造或函数体运行。
- class_body_definition_time：执行类体语句的阶段；方法体不会在定义时运行。
- delayed_function_body：函数/方法体中的调用语法记录，明示为延迟到调用时执行。

导入记录也包含 context，用于区分模块体导入和条件/类体/函数体内导入。本次 15 个文件中的导入项均位于模块体，没有条件导入；这只描述固定源码 AST，不推断动态导入。

## 依赖解析边界

项目导入若可解析到固定仓库中的 .py/包 __init__.py，记录源码路径与 SHA 并递归。外部项仅静态定位指定环境中直接点名模块的源码文件或包入口，并记录 Torch、Transformers、SciPy、NumPy、scikit-learn 的 dist-info 元数据 SHA/版本。Transformers 的惰性导出（如 PBT.py 第12至14行的 Llama/GPT/Auto 类）只定位到包入口，不能据此闭合各模型实现、patched Llama 变体或其全部传递依赖；原生扩展、运行时分支、导入钩子、动态生成模块及依赖的完整运行期行为不穷尽。

同时对固定仓库 requirements.txt 做了纯文本版本与指定环境 dist-info 存在性比对；它不是安装兼容性或运行时验证。若 requirements 中某发行版没有匹配 dist-info，JSON 明确列出。例如 BatteryML==0.0.1、evaluate==0.4.3、peft==0.12.0、reformer_pytorch==1.4.4 在该环境元数据中无匹配。项目闭包还可见 layers/SelfAttention_Family.py 第6行导入 reformer_pytorch，utils/tools.py 第8行导入 evaluate；它们的导入存在性不等同于模型路径必然调用这些模块，但也不能据此声称常规 PBT 模块导入已在该环境验证。报告保留该环境不匹配风险。

## tokenizer 与 PCA 省略影响

原构造器 PBT.py 第487至493行使用本地 AutoTokenizer.from_pretrained，设置 trust_remote_code=True、local_files_only=True 与 pad token；PBT.py 第498行写入 padding_side='right'。省略这些操作会跳过 tokenizer/config/vocab 解析和对象元数据初始化。即使固定源码中未见 tokenizer 被 forward 直接使用，也不能排除自定义模型代码、tokenizer 元数据、全局注册、hook 或其他间接效果。是否消耗 RNG、注册 hooks/module、影响全局状态或本流程 metadata：未证。

PBT.py 第519行通过 pickle.load(open(configs.pca_path, 'rb')) 载入 PCA 对象。这里没有读取该 pickle，也没有执行其 reducer/重建逻辑；载入对象带来的任意副作用、RNG 使用、hooks/module 注册及 metadata 影响均未证。省略 tokenizer/PCA 不构成参数初始化随机序列或对象状态等价的证明。已证与未证依据分列，未作 不是 nn.Module之类推测。

## 执行边界与下一步

本审计没有导入任何项目模块、Torch、Transformers 或其他依赖；没有打开 checkpoint/PCA/验证大二进制，没有调用 pickle/joblib/torch.load，没有新解码 195 个 embedding，没有构造模型、strict load、forward、metrics、test、fit。此项审计未执行模型计算，new_fits=0、optimizer_steps=0。

供主控下一步审查：逐项复核 definition-time 和 module-body 节点；结合 tokenizer 固定本地资产与任意 pickle 重建风险，提出保留原构造行为的最小有界验证计划。只有主控另行明确授权后才能考虑执行；本报告不提供该授权。

## 可复核文件

- 固定源：repos/pinned/PBT_122077bc5435bb0ba5406f2b112fa96903a08c6a/models/PBT.py
- inactive proposal：reports/pbt_minimal_constructor_proposal_v1_root/proposal.json
- 当前合同：reports/pbt_author_eol_val_contract_v3_root/contract_v3.json
- 既有直接引用审计：reports/pbt_constructor_dependency_static_v2/constructor_static_audit.json

闭包中另外发现 configuration_BatteryLifeLLM.py 第17行也调用 transformers.logging.set_verbosity_error()，utils/tools.py 第16行调用 plt.switch_backend()；后者改变 Matplotlib 后端。它们是递归项目源码模块的模块体调用。外部包直接导入在该环境不可解析的项包括 reformer_pytorch、evaluate、wandb；requirements 中没有 wandb 条目。requirements 的 dist-info 检查仅按发行版名称匹配，不比较版本，也不证明依赖可运行。
