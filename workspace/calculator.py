"""一个故意留了 bug 的小计算器，用于演示 Agent 的读改跑闭环。"""


def add(a, b):
    return a + b


def divide(a, b):
    return a / b


def average(nums):
    # 空列表没有平均值，返回 0.0 而不是抛 ZeroDivisionError
    if not nums:
        return 0.0
    return sum(nums) / len(nums)


if __name__ == "__main__":
    print("1 + 2 =", add(1, 2))
    print("10 / 2 =", divide(10, 2))
    print("average([1, 2, 3]) =", average([1, 2, 3]))
    print("average([]) =", average([]))
