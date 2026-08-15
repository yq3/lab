// 类型声明：opencode-config.mjs 的导出（仅供前端 tsc 类型检查；不随 install 脚本拷贝）。

export interface ConfigToolOptions {
  pluginName?: string;
  marker?: string;
}

export function mergePlugin(text: string, options?: ConfigToolOptions): string;

export function uninstallPlugin(text: string, options?: ConfigToolOptions): string;
