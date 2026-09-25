# 第三方组件说明

以下依据本地实际安装包元数据整理。它们提供HTTP、类型校验、Office解析和图表等基础功能；不得作为团队原创功能申报。分发依赖时同时保留上游包中的声明。

| 包 | 当前验证版本 | 包元数据许可 | 本地许可证副本 |
| --- | --- | --- | --- |
| fastapi | 0.141.1 | MIT | [fastapi-LICENSE](third_party/licenses/fastapi-LICENSE) |
| starlette | 1.6.0 | BSD-3-Clause | [starlette-LICENSE.md](third_party/licenses/starlette-LICENSE.md) |
| uvicorn | 0.53.0 | BSD-3-Clause | [uvicorn-LICENSE.md](third_party/licenses/uvicorn-LICENSE.md) |
| pydantic | 2.13.5 | MIT | [pydantic-LICENSE](third_party/licenses/pydantic-LICENSE) |
| python-multipart | 0.0.32 | Apache-2.0 | [python-multipart-LICENSE.txt](third_party/licenses/python-multipart-LICENSE.txt) |
| openpyxl | 3.1.5 | MIT | 上游历史仓库许可副本 [LICENCE.rst](third_party/licenses/openpyxl-LICENCE.rst)，正式分发核对所用版本源码包 |
| python-docx | 1.2.0 | MIT | [python-docx-LICENSE](third_party/licenses/python-docx-LICENSE) |
| python-pptx | 1.0.2 | MIT | [python-pptx-LICENSE](third_party/licenses/python-pptx-LICENSE) |
| httpx | 0.28.1 | BSD-3-Clause | [httpx-LICENSE.md](third_party/licenses/httpx-LICENSE.md) |
| lxml | 6.1.1 | BSD-3-Clause | [lxml-LICENSE.txt](third_party/licenses/lxml-LICENSE.txt)、[lxml-LICENSES.txt](third_party/licenses/lxml-LICENSES.txt) |
| Pillow | 12.3.0 | MIT-CMU | [Pillow-LICENSE](third_party/licenses/Pillow-LICENSE) |
| XlsxWriter | 3.2.9 | BSD-2-Clause | [XlsxWriter-LICENSE.txt](third_party/licenses/XlsxWriter-LICENSE.txt) |

WPS和Microsoft Office软件及其SDK均未打包或调用。文档、数据、字体、模型权重和外部服务具有独立的使用条件，不由上述代码许可覆盖。

依赖许可清单用于工程记录，不是法律意见。此清单不等于完整的传递依赖审计；发布前还需根据锁定环境保存全部分发包所需声明。
