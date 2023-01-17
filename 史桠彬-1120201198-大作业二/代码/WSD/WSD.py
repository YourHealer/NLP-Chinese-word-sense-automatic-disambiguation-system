import os
import jieba
import sqlite3
import requests
import urllib.parse
from PyQt5 import uic
from math import log2
from bs4 import BeautifulSoup
from pyltp import SentenceSplitter
from PyQt5.QtWidgets import QApplication

class Stats:
    def __init__(self):
        # 从文件中加载UI定义
        self.ui = uic.loadUi("myWindow.ui")
        # 按钮禁用
        self.ui.pushButton_2.setEnabled(False)
        self.ui.pushButton_3.setEnabled(False)
        # 定义不同按钮的槽函数
        self.ui.pushButton.clicked.connect(self.getInfo)
        self.ui.pushButton_2.clicked.connect(self.ensure)
        self.ui.pushButton_3.clicked.connect(self.ensure)

    def ensure(self):
        # 连接数据库
        conn = sqlite3.connect('myLink.db')
        cur = conn.cursor()
        with conn:
            #获取据用户自行判断的预测结果
            if self.ui.sender() == self.ui.pushButton_2:
                right = 1
            elif self.ui.sender() == self.ui.pushButton_3:
                right = 0
            # 获取原文本和消歧词
            text = self.ui.plainTextEdit.toPlainText()
            word = self.ui.lineEdit.text()
            predict = self.ui.lineEdit_2.text()

            cur.execute("select * from myCounter WHERE 是否正确=1")
            res_right = len(cur.fetchall()) + right

            cur.execute("select * from myCounter")
            res_total = len(cur.fetchall()) + 1

            # 计算目前正确率
            percent = str(round(res_right / res_total * 100, 1)) + "%"

            # 将结果存入数据库
            cur.execute("""INSERT INTO myCounter VALUES (?,?,?,?,?)""", (text, word, predict, right, percent))

    def getInfo(self):

        # 获取待消歧文本sent和歧义词wsd_word
        sent = self.ui.plainTextEdit.toPlainText()
        wsd_word = self.ui.lineEdit.text()

        myList = []

        # 利用爬虫获取基于百度百科的语义基址starturl
        base_url = "https://baike.baidu.com"
        quote = urllib.parse.quote(wsd_word, encoding="utf-8")
        starturl = base_url + "/item/" + quote
        myList.append(starturl)

        # 利用爬虫获取其余语义变址的列表ans，并对各网址进行遍历
        ans = str(WebScrape(wsd_word, starturl).get_all_gloss()).split()
        for i in ans:
            if ('href=' in i):
                myUrl = base_url + i.strip("href=\"")
                if ('>' not in myUrl):
                    myList.append(myUrl)

        # 对歧义词所有语义在百度百科网站中的网址进行爬取，获得不同义项的语料
        for i in myList:
            url = i
            WebScrape(wsd_word, url).run()

        # 向分词词典添加歧义词便于分词，并选用精确模式进行分词
        jieba.add_word(wsd_word)
        sent_words = list(jieba.cut(sent, cut_all=False))

        # 加入“哈工大停用词词库”、“四川大学机器学习智能实验室停用词库”、百度停用词表“等各种停用词表的综合停用词表
        with open('stopwprd.txt', 'r', encoding='utf-8') as f:
            stopwords = [_.strip() for _ in f.readlines()]
        stopwords.append(wsd_word)

        # 将分词结果中的停用词剔除
        sent_cut = []
        for word in sent_words:
            if word not in stopwords:
                sent_cut.append(word)
        print(sent_cut)
        print()

        # 计算词的TF-IDF以及频数
        wsd_dict = {}
        for file in os.listdir('./' + wsd_word):
            if wsd_word in file:
                wsd_dict[file.replace('.txt', '')] = read_file(wsd_word + '/' + file)

        # 统计每个词语在语料中出现的次数
        tf_dict = {}
        for meaning, sents in wsd_dict.items():
            tf_dict[meaning] = []
            for word in sent_cut:
                word_count = 0
                for sent in sents:
                    example = list(jieba.cut(sent, cut_all=False))
                    word_count += example.count(word)

                if word_count:
                    tf_dict[meaning].append((word, word_count))

        idf_dict = {}
        for word in sent_cut:
            document_count = 0
            for meaning, sents in wsd_dict.items():
                for sent in sents:
                    if word in sent:
                        document_count += 1

            idf_dict[word] = document_count

        # 输出值
        total_document = 0
        for meaning, sents in wsd_dict.items():
            total_document += len(sents)

        # 计算TF_IDF值
        mean_tf_idf = []
        for k, v in tf_dict.items():
            tf_idf_sum = 0
            for item in v:
                word = item[0]
                tf = item[1]
                tf_idf = item[1] * log2(total_document / (1 + idf_dict[word]))
                tf_idf_sum += tf_idf

            mean_tf_idf.append((k, tf_idf_sum))

        # 对不同词义的可能概率排序
        sort_array = sorted(mean_tf_idf, key=lambda x: x[1], reverse=True)

        # 根据词频及TF-IDF值确定是否有歧义及最大概率的语义
        if (len(sort_array) == 0):
            # 按钮启用
            self.ui.lineEdit_2.setText("该词语无歧义。")
        else:
            if sort_array[0][1] == 0:
                self.ui.lineEdit_2.setText("该文本信息量不足，无法判断语义。")
            else:
                # 按钮启用
                self.ui.pushButton_2.setEnabled(True)
                self.ui.pushButton_3.setEnabled(True)
                print("所有可能语义及对应TF-IDF值为：")
                for i in sort_array:
                    print(i)
                true_meaning = sort_array[0][0].split('_')[1]
                self.ui.lineEdit_2.setText(wsd_word + "-" + true_meaning)

class WebScrape(object):
    def __init__(self, word, url):
        self.url = url
        self.word = word

    # 爬取百度百科页面
    def web_parse(self):
        # 指定headers
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Safari/537.36'}
        req = requests.get(url=self.url, headers=headers)

        # 解析网页，定位到main-content部分
        if req.status_code == 200:
            soup = BeautifulSoup(req.text.encode(req.encoding), 'lxml')
            return soup
        return None

    # 获取该词语的全部义项
    def get_all_gloss(self):
        soup = self.web_parse()
        if soup:
            lis = soup.find('ul', class_="polysemantList-wrapper cmn-clearfix")
            return lis

    # 获取指定网站的义项
    def get_gloss(self):
        soup = self.web_parse()
        if soup:
            lis = soup.find('ul', class_="polysemantList-wrapper cmn-clearfix")
            if lis:
                for li in lis('li'):
                    if '<a' not in str(li):
                        gloss = li.text.replace('▪', '')
                        return gloss
        return None

    # 获取该义项的语料，以句子为单位
    def get_content(self):
        # 发送HTTP请求
        result = []
        soup = self.web_parse()
        if soup:
            paras = soup.find('div', class_='main-content').text.split('\n')
            for para in paras:
                if self.word in para:
                    sents = list(SentenceSplitter.split(para))
                    for sent in sents:
                        if self.word in sent:
                            sent = sent.replace('\xa0', '').replace('\u3000', '')
                            result.append(sent)
        result = list(set(result))
        return result

    # 将该义项的语料写入到txt
    def write_2_file(self):
        gloss = self.get_gloss()
        result = self.get_content()
        path = r'./'+ self.word
        if(os.path.exists(path) == False):
            os.mkdir(path)
        if result and gloss:
            with open('./' + self.word +'/%s_%s.txt' % (self.word, gloss), 'w', encoding='utf-8') as f:
                f.writelines([_ + '\n' for _ in result])

    # 运行
    def run(self):
        self.write_2_file()

# 读取每个义项的语料
def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = [_.strip() for _ in f.readlines()]
        return lines

app = QApplication([])
stats = Stats()
stats.ui.show()
app.exec_()