import matplotlib.pyplot as plt

categories = [
    "Databases & Queries", "Statistical Tools", "Natural Language Understanding", "Recommendation Models", "Geography & Travel"
]

values = [11, 10, 6, 6, 6]

plt.figure(figsize=(12, 6))
plt.bar(categories, values, color='skyblue')
plt.xticks(rotation=45, ha='right')
plt.ylabel('Number of Tools / Percentage')
plt.title('Category Distribution of Tools')
plt.tight_layout()
plt.savefig('category_distribution.png')



plt.figure(figsize=(8, 8))
plt.pie(values, labels=categories, autopct='%1.1f%%', startangle=140)
plt.title('Category Distribution of Tools')
plt.axis('equal')  # 确保饼图是圆�?plt.savefig('category_distribution_pie.png')
