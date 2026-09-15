"""泛型函数——3.12 的方括号语法（PEP 695）：def 名字[类型参数](参数) -> 返回。"""


def first[T](items: list[T]) -> T:
    """取第一个元素；空列表是调用方错误，直接抛。

    对照 Java：public static <T> T first(List<T> items)。
    调用处不需要写类型参数：first([3, 1, 2]) 里 T 自动绑定 int。
    """
    if not items:
        raise ValueError("first() 不接受空列表")
    return items[0]


def pluck[K, V](rows: list[dict[K, V]], key: K) -> list[V]:
    """从一组同形 dict 里取同一个键的值（工具函数常客，两个类型参数的示范）。

    对照 Java：public static <K, V> List<V> pluck(List<Map<K, V>> rows, K key)。
    """
    return [row[key] for row in rows]
