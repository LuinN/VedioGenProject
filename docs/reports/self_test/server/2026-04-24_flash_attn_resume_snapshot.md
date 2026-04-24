# 2026-04-24 flash_attn 可续编快照

## 结论

- 当前 `flash_attn` 本地编译已从 `pip` 的临时目录切换为仓库内持久源码树
- 当前编译进程已在 `2026-04-24 02:46:53 +0800` 主动停止
- 明天重新启动 Codex 后，不需要回到 `pip install` 的 `/tmp/pip-install-*` 临时目录从零开始

## 持久目录

- 源码目录：`code/server/wan_local_service/third_party/flash-attn-2.8.3-src`
- wheel 目录：`code/server/wan_local_service/storage/flash_attn_wheels`
- 续编脚本：`code/server/wan_local_service/scripts/build_flash_attn_resumable.sh`

## 当前编译进度

- 已完成 `.o` 目标：`22 / 73`
- 最新 `.o`：
  - `2026-04-24 02:41:33.1185762990 ./csrc/flash_attn/src/flash_bwd_hdim96_bf16_causal_sm80.o`
- 说明：
  - 原始 `pip` 临时目录在停止后已被自动清理
  - 但第一次全量快照已保留到仓库内持久源码树，`build/` 目录仍在
  - 后续续编应统一基于持久源码树完成

## 明天继续的命令

```bash
cd code/server/wan_local_service
bash scripts/build_flash_attn_resumable.sh status
WAN_FLASH_ATTN_MAX_JOBS=1 bash scripts/build_flash_attn_resumable.sh resume
```

如果你希望继续走一体化安装脚本，也可以直接执行：

```bash
cd code/server/wan_local_service
WAN_FLASH_ATTN_MAX_JOBS=1 bash scripts/setup_wan22.sh
```

当前 `setup_wan22.sh` 已改为复用同一份持久源码树。
