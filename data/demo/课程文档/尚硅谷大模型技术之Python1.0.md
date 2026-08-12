# Python 程序设计（演示讲义）

## 课程定位

本课程面向零基础学员，系统讲解 Python 基础语法、流程控制、函数与常用数据结构，
并通过大量小练习帮助学员建立编程思维，是后续大模型开发、数据分析等课程的前置基础。

## 变量与数据类型

Python 中的变量不需要显式声明类型，赋值即创建。
常见数据类型包括：整数（int）、浮点数（float）、字符串（str）、布尔值（bool）、列表（list）、元组（tuple）、字典（dict）与集合（set）。

```python
name = "张三"
age = 18
score = 92.5
is_pass = score >= 60
```

## 流程控制

### 条件判断

```python
if score >= 90:
    print("优秀")
elif score >= 60:
    print("及格")
else:
    print("不及格")
```

### 循环

`for` 循环适合遍历可迭代对象，`while` 循环适合在条件满足时重复执行。
`break` 提前结束循环，`continue` 跳过本次循环进入下一次。

```python
total = 0
for i in range(1, 101):
    total += i
print(total)
```

## 函数

函数用于封装可复用的逻辑，参数让函数具备输入能力，`return` 返回结果。

```python
def add(a, b):
    return a + b
```

## 列表与字典

列表保存有序数据，字典保存键值映射。它们都是 Python 中最常用的容器类型。

```python
courses = ["Python", "机器学习", "深度学习"]
student = {"name": "张三", "age": 18}
```

## 常用练习题

1. 编写函数统计字符串中元音字母的个数。
2. 编写函数对整数列表去重并保持首次出现顺序。
3. 编写函数判断一个字符串是否为回文（忽略空格与大小写）。
