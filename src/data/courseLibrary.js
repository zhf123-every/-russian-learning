export const LEVELS = ['A1', 'A2', 'B1', 'B2']

export const courseLibrary = {
  A1: {
    collections: [
      {
        id: 'a1_greetings',
        name: '俄语入门：日常问候',
        description: '从最基础的问候语开始，涵盖见面、告别、感谢、道歉等日常场景。',
        videos: [
          {
            id: 'a1_greet_01',
            title: '俄语第一课：问候与自我介绍',
            description: '学习最基础的俄语问候语、自我介绍句型，零基础入门。',
            thumbnail: 'https://picsum.photos/seed/ru_greet_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_greet_01/1280/720',
            level: 'A1',
            duration: '4:30',
            words: 120,
            tags: ['慢速', '基础', '口语'],
            learners: 128,
            sentences: [
              { id: 1, russian: 'Здра́вствуйте!', chinese: '您好！' },
              { id: 2, russian: 'Приве́т!', chinese: '你好！（非正式）' },
              { id: 3, russian: 'До́брое у́тро!', chinese: '早上好！' },
              { id: 4, russian: 'До́брый день!', chinese: '你好！（白天）' },
              { id: 5, russian: 'До́брый ве́чер!', chinese: '晚上好！' },
              { id: 6, russian: 'Как у вас дела́?', chinese: '您最近怎么样？' },
              { id: 7, russian: 'Хорошо́, спаси́бо.', chinese: '很好，谢谢。' },
              { id: 8, russian: 'Меня́ зову́т А́нна.', chinese: '我叫安娜。' },
              { id: 9, russian: 'Как вас зову́т?', chinese: '您叫什么名字？' },
              { id: 10, russian: 'О́чень прия́тно!', chinese: '很高兴认识您！' },
              { id: 11, russian: 'До свида́ния!', chinese: '再见！' },
              { id: 12, russian: 'Пока́!', chinese: '拜拜！（非正式）' },
              { id: 13, russian: 'Спаси́бо большо́е!', chinese: '非常感谢！' },
              { id: 14, russian: 'Пожа́луйста.', chinese: '不客气。／请。' },
              { id: 15, russian: 'Извини́те, пожа́луйста.', chinese: '对不起，打扰一下。' }
            ]
          }
        ]
      },
      {
        id: 'a1_intro',
        name: '俄语基础：自我介绍与数字',
        description: '学会介绍自己、家人朋友，表达年龄、职业和基本喜好。',
        videos: [
          {
            id: 'a1_intro_01',
            title: '俄语第二课：我的自我介绍',
            description: '学习自我介绍、职业、年龄与家庭关系的常用表达。',
            thumbnail: 'https://picsum.photos/seed/ru_intro_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_intro_01/1280/720',
            level: 'A1',
            duration: '5:10',
            words: 140,
            tags: ['基础', '口语', '自我介绍'],
            learners: 96,
            sentences: [
              { id: 1, russian: 'Я студе́нт.', chinese: '我是学生。' },
              { id: 2, russian: 'Я из Кита́я.', chinese: '我来自中国。' },
              { id: 3, russian: 'Я говорю́ по-ру́сски немно́го.', chinese: '我会说一点俄语。' },
              { id: 4, russian: 'Мне два́дцать лет.', chinese: '我二十岁。' },
              { id: 5, russian: 'Э́то мой друг.', chinese: '这是我的朋友。' },
              { id: 6, russian: 'Он у́чится в университе́те.', chinese: '他在大学学习。' },
              { id: 7, russian: 'Она́ рабо́тает в шко́ле.', chinese: '她在学校工作。' },
              { id: 8, russian: 'Мы живём в Москве́.', chinese: '我们住在莫斯科。' },
              { id: 9, russian: 'У меня́ есть сестра́.', chinese: '我有一个姐妹。' },
              { id: 10, russian: 'У меня́ нет бра́та.', chinese: '我没有兄弟。' },
              { id: 11, russian: 'Э́то о́чень интере́сно.', chinese: '这很有趣。' },
              { id: 12, russian: 'Я люблю́ чита́ть.', chinese: '我喜欢阅读。' },
              { id: 13, russian: 'Я учу́ ру́сский язы́к.', chinese: '我在学俄语。' },
              { id: 14, russian: 'Повтори́те, пожа́луйста.', chinese: '请再说一遍。' },
              { id: 15, russian: 'Я не понима́ю.', chinese: '我不明白。' }
            ]
          }
        ]
      },
      {
        id: 'a1_basics',
        name: '俄语基础：数字、颜色与物品',
        description: '掌握数字、颜色和常见物品的表达，学会询问价格与描述事物。',
        videos: [
          {
            id: 'a1_basics_01',
            title: '俄语第三课：数字与颜色',
            description: '学习数字、颜色、常见物品与购物中的基本表达。',
            thumbnail: 'https://picsum.photos/seed/ru_basics_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_basics_01/1280/720',
            level: 'A1',
            duration: '4:50',
            words: 130,
            tags: ['基础', '数字', '物品'],
            learners: 88,
            sentences: [
              { id: 1, russian: 'Оди́н, два, три.', chinese: '一，二，三。' },
              { id: 2, russian: 'Мне ну́жно пять я́блок.', chinese: '我需要五个苹果。' },
              { id: 3, russian: 'Э́то кра́сный цвет.', chinese: '这是红色。' },
              { id: 4, russian: 'У меня́ есть си́няя ру́чка.', chinese: '我有一支蓝色的笔。' },
              { id: 5, russian: 'Ско́лько э́то сто́ит?', chinese: '这个多少钱？' },
              { id: 6, russian: 'Э́то сто́ит сто рубле́й.', chinese: '这个一百卢布。' },
              { id: 7, russian: 'Я ви́жу большо́й дом.', chinese: '我看见一栋大房子。' },
              { id: 8, russian: 'Э́то моя́ кни́га.', chinese: '这是我的书。' },
              { id: 9, russian: 'У тебя́ есть каранда́ш?', chinese: '你有铅笔吗？' },
              { id: 10, russian: 'Дай мне, пожа́луйста, стака́н воды́.', chinese: '请给我一杯水。' },
              { id: 11, russian: 'Э́тот стол деревя́нный.', chinese: '这张桌子是木头的。' },
              { id: 12, russian: 'Мне нра́вится зелёный цвет.', chinese: '我喜欢绿色。' },
              { id: 13, russian: 'У нас три́дцать уче́ников.', chinese: '我们有三十名学生。' },
              { id: 14, russian: 'Э́то о́чень до́рого.', chinese: '这太贵了。' },
              { id: 15, russian: 'Я хочу́ купи́ть но́вый телефо́н.', chinese: '我想买一部新手机。' }
            ]
          }
        ]
      }
    ]
  },
  A2: {
    collections: [
      {
        id: 'a2_past',
        name: '俄语进阶：过去时与生活',
        description: '用过去时描述日常生活、经历和天气，练习动词过去时态。',
        videos: [
          {
            id: 'a2_past_01',
            title: '日常生活：昨天我做了什么',
            description: '学习俄语过去时，描述昨天和过去的日常活动。',
            thumbnail: 'https://picsum.photos/seed/ru_past_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_past_01/1280/720',
            level: 'A2',
            duration: '6:00',
            words: 160,
            tags: ['过去时', '生活', '语法'],
            learners: 74,
            sentences: [
              { id: 1, russian: 'Вчера́ я ходи́л в кино́.', chinese: '昨天我去看电影了。' },
              { id: 2, russian: 'У́тром я встал в семь часо́в.', chinese: '早上我七点起床。' },
              { id: 3, russian: 'Мы гуля́ли в па́рке.', chinese: '我们在公园散步。' },
              { id: 4, russian: 'Она́ гото́вила у́жин.', chinese: '她做了晚饭。' },
              { id: 5, russian: 'Я чита́л кни́гу весь ве́чер.', chinese: '我整个晚上都在读书。' },
              { id: 6, russian: 'Он рабо́тал це́лый день.', chinese: '他工作了一整天。' },
              { id: 7, russian: 'Мы смотре́ли телеви́зор.', chinese: '我们看电视了。' },
              { id: 8, russian: 'Я купи́л хлеб и молоко́.', chinese: '我买了面包和牛奶。' },
              { id: 9, russian: 'Она́ позвони́ла подру́ге.', chinese: '她给朋友打了电话。' },
              { id: 10, russian: 'Мы отдыха́ли на мо́ре.', chinese: '我们在海边休息。' },
              { id: 11, russian: 'Я был о́чень за́нят.', chinese: '我当时很忙。' },
              { id: 12, russian: 'Пого́да была́ хоро́шая.', chinese: '天气很好。' },
              { id: 13, russian: 'Мы хорошо́ провели́ вре́мя.', chinese: '我们度过了愉快的时光。' },
              { id: 14, russian: 'Я забы́л свои́ ключи́.', chinese: '我忘了我的钥匙。' },
              { id: 15, russian: 'Он рассказа́л интере́сную исто́рию.', chinese: '他讲了一个有趣的故事。' }
            ]
          }
        ]
      },
      {
        id: 'a2_future',
        name: '俄语进阶：未来计划与愿望',
        description: '用将来时描述计划、打算和愿望，练习未完成体和完成体将来时。',
        videos: [
          {
            id: 'a2_future_01',
            title: '未来计划：明天我要做什么',
            description: '学习俄语将来时，描述计划、梦想和未来的打算。',
            thumbnail: 'https://picsum.photos/seed/ru_future_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_future_01/1280/720',
            level: 'A2',
            duration: '6:10',
            words: 150,
            tags: ['将来时', '计划', '生活'],
            learners: 69,
            sentences: [
              { id: 1, russian: 'За́втра я пое́ду в го́род.', chinese: '明天我要去城里。' },
              { id: 2, russian: 'Ле́том мы пое́дем на мо́ре.', chinese: '夏天我们要去海边。' },
              { id: 3, russian: 'Я бу́ду учи́ть ру́сский язы́к.', chinese: '我要学俄语。' },
              { id: 4, russian: 'Она́ хо́чет стать врачо́м.', chinese: '她想当医生。' },
              { id: 5, russian: 'Мы бу́дем жить в Москве́.', chinese: '我们将住在莫斯科。' },
              { id: 6, russian: 'Я плани́рую пое́хать за грани́цу.', chinese: '我计划出国。' },
              { id: 7, russian: 'В бу́дущем году́ я найду́ но́вую рабо́ту.', chinese: '明年我会找新工作。' },
              { id: 8, russian: 'Он собира́ется жени́ться.', chinese: '他打算结婚。' },
              { id: 9, russian: 'Я мечта́ю путеше́ствовать по ми́ру.', chinese: '我梦想环游世界。' },
              { id: 10, russian: 'Мы встре́тимся за́втра ве́чером.', chinese: '我们明晚见面。' },
              { id: 11, russian: 'Ско́ро начну́тся кани́кулы.', chinese: '假期快到了。' },
              { id: 12, russian: 'Я хочу́ вы́учить но́вый язы́к.', chinese: '我想学一门新语言。' },
              { id: 13, russian: 'Она́ бу́дет рабо́тать за грани́цей.', chinese: '她将在国外工作。' },
              { id: 14, russian: 'Мы реши́ли перее́хать в друго́й го́род.', chinese: '我们决定搬到另一个城市。' },
              { id: 15, russian: 'Я наде́юсь, что всё полу́чится.', chinese: '我希望一切顺利。' }
            ]
          }
        ]
      },
      {
        id: 'a2_hobbies',
        name: '俄语进阶：兴趣与爱好',
        description: '谈论兴趣爱好、业余活动，练习表达喜好与能力。',
        videos: [
          {
            id: 'a2_hobbies_01',
            title: '兴趣爱好：我周末喜欢做什么',
            description: '学习用俄语谈论爱好、特长和空闲时间安排。',
            thumbnail: 'https://picsum.photos/seed/ru_hobbies_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_hobbies_01/1280/720',
            level: 'A2',
            duration: '5:30',
            words: 140,
            tags: ['爱好', '生活', '口语'],
            learners: 62,
            sentences: [
              { id: 1, russian: 'Моё хо́бби — фотогра́фия.', chinese: '我的爱好是摄影。' },
              { id: 2, russian: 'Я увлека́юсь му́зыкой.', chinese: '我热爱音乐。' },
              { id: 3, russian: 'В свобо́дное вре́мя я рису́ю.', chinese: '空闲时我画画。' },
              { id: 4, russian: 'Он игра́ет на гита́ре.', chinese: '他弹吉他。' },
              { id: 5, russian: 'Я люблю́ чита́ть кни́ги.', chinese: '我喜欢读书。' },
              { id: 6, russian: 'Мы ча́сто хо́дим в теа́тр.', chinese: '我们经常去剧院。' },
              { id: 7, russian: 'Она́ занима́ется пла́ванием.', chinese: '她游泳。' },
              { id: 8, russian: 'Мне нра́вится смотре́ть фи́льмы.', chinese: '我喜欢看电影。' },
              { id: 9, russian: 'По выходны́м я гуля́ю в па́рке.', chinese: '周末我在公园散步。' },
              { id: 10, russian: 'Я собира́ю ма́рки.', chinese: '我集邮。' },
              { id: 11, russian: 'Он увлека́ется футбо́лом.', chinese: '他喜欢足球。' },
              { id: 12, russian: 'Мы лю́бим гото́вить вме́сте.', chinese: '我们喜欢一起做饭。' },
              { id: 13, russian: 'Она́ хорошо́ танцу́ет.', chinese: '她跳舞很好。' },
              { id: 14, russian: 'Я хочу́ научи́ться игра́ть на пиани́но.', chinese: '我想学弹钢琴。' },
              { id: 15, russian: 'Э́то моё люби́мое заня́тие.', chinese: '这是我最喜欢的事。' }
            ]
          }
        ]
      }
    ]
  },
  B1: {
    collections: [
      {
        id: 'b1_opinion',
        name: '俄语中级：观点与论证',
        description: '学习表达观点、同意与反驳、权衡利弊，提升逻辑表达能力。',
        videos: [
          {
            id: 'b1_opinion_01',
            title: '表达观点：我同意还是反对',
            description: '学习用俄语表达个人观点、权衡利弊和进行讨论。',
            thumbnail: 'https://picsum.photos/seed/ru_opinion_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_opinion_01/1280/720',
            level: 'B1',
            duration: '7:20',
            words: 200,
            tags: ['观点', '讨论', '中级'],
            learners: 51,
            sentences: [
              { id: 1, russian: 'По-мо́ему, э́то пра́вильное реше́ние.', chinese: '在我看来，这是正确的决定。' },
              { id: 2, russian: 'Я счита́ю, что на́до бо́льше занима́ться.', chinese: '我认为需要多练习。' },
              { id: 3, russian: 'С одно́й стороны́, э́то поле́зно.', chinese: '一方面，这很有用。' },
              { id: 4, russian: 'С друго́й стороны́, э́то до́рого.', chinese: '另一方面，这很贵。' },
              { id: 5, russian: 'Мне ка́жется, он прав.', chinese: '我觉得他是对的。' },
              { id: 6, russian: 'Я не согла́сен с э́тим мне́нием.', chinese: '我不同意这个观点。' },
              { id: 7, russian: 'Э́то зави́сит от мно́гих фа́кторов.', chinese: '这取决于许多因素。' },
              { id: 8, russian: 'Ва́жно понима́ть причи́ны.', chinese: '理解原因很重要。' },
              { id: 9, russian: 'Я ду́маю, что э́то возмо́жно.', chinese: '我认为这是可能的。' },
              { id: 10, russian: 'На мой взгляд, э́то сли́шком сло́жно.', chinese: '在我看来，这太复杂了。' },
              { id: 11, russian: 'На́до учи́тывать все обстоя́тельства.', chinese: '需要考虑所有情况。' },
              { id: 12, russian: 'Я убеждён, что э́то пра́вильно.', chinese: '我确信这是正确的。' },
              { id: 13, russian: 'К сожале́нию, э́то невозмо́жно.', chinese: '很遗憾，这是不可能的。' },
              { id: 14, russian: 'Мне интере́сно узна́ть ва́ше мне́ние.', chinese: '我很想知道你的看法。' },
              { id: 15, russian: 'Дава́йте обсу́дим э́ту пробле́му.', chinese: '让我们讨论一下这个问题。' }
            ]
          }
        ]
      },
      {
        id: 'b1_travel',
        name: '俄语中级：旅行与经历',
        description: '讲述旅行经历、旅途见闻，练习过去时叙述与细节描写。',
        videos: [
          {
            id: 'b1_travel_01',
            title: '旅行见闻：我去过的地方',
            description: '用俄语讲述旅行经历、文化见闻与难忘的瞬间。',
            thumbnail: 'https://picsum.photos/seed/ru_travel_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_travel_01/1280/720',
            level: 'B1',
            duration: '7:00',
            words: 190,
            tags: ['旅行', '经历', '过去时'],
            learners: 47,
            sentences: [
              { id: 1, russian: 'В про́шлом году́ я был в Санкт-Петербу́рге.', chinese: '去年我去过圣彼得堡。' },
              { id: 2, russian: 'Путеше́ствия расширя́ют кругозо́р.', chinese: '旅行开阔眼界。' },
              { id: 3, russian: 'Я люблю́ узнава́ть но́вые культу́ры.', chinese: '我喜欢了解新文化。' },
              { id: 4, russian: 'Мы заброни́ровали оте́ль в це́нтре го́рода.', chinese: '我们预订了市中心的酒店。' },
              { id: 5, russian: 'Доро́га заняла́ о́коло пяти́ часо́в.', chinese: '路上花了大约五个小时。' },
              { id: 6, russian: 'Мне понра́вилась ме́стная ку́хня.', chinese: '我喜欢当地的美食。' },
              { id: 7, russian: 'Мы посети́ли мно́го музе́ев.', chinese: '我们参观了许多博物馆。' },
              { id: 8, russian: 'Я сде́лал мно́го краси́вых фотогра́фий.', chinese: '我拍了许多漂亮的照片。' },
              { id: 9, russian: 'Путеше́ствовать самому́ интере́снее.', chinese: '独自旅行更有趣。' },
              { id: 10, russian: 'Э́та пое́здка была́ незабыва́емой.', chinese: '这次旅行令人难忘。' },
              { id: 11, russian: 'Мы познако́мились с ме́стными жи́телями.', chinese: '我们认识了当地人。' },
              { id: 12, russian: 'Я предпочита́ю путеше́ствовать по́ездом.', chinese: '我更喜欢坐火车旅行。' },
              { id: 13, russian: 'В сле́дующий раз я пое́ду в Каза́нь.', chinese: '下次我要去喀山。' },
              { id: 14, russian: 'Э́тот го́род произвёл на меня́ большо́е впечатле́ние.', chinese: '这座城市给我留下了深刻印象。' },
              { id: 15, russian: 'Я сове́тую вам посети́ть э́то ме́сто.', chinese: '我建议您去这个地方。' }
            ]
          }
        ]
      },
      {
        id: 'b1_health',
        name: '俄语中级：健康与习惯',
        description: '谈论健康、生活习惯与养生，学习表达建议与原因。',
        videos: [
          {
            id: 'b1_health_01',
            title: '健康生活：我的日常习惯',
            description: '用俄语谈论健康、作息、运动与饮食等生活习惯。',
            thumbnail: 'https://picsum.photos/seed/ru_health_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_health_01/1280/720',
            level: 'B1',
            duration: '6:40',
            words: 180,
            tags: ['健康', '习惯', '生活'],
            learners: 44,
            sentences: [
              { id: 1, russian: 'Здоро́вье — са́мое гла́вное.', chinese: '健康是最重要的。' },
              { id: 2, russian: 'Я стара́юсь вести́ здоро́вый о́браз жи́зни.', chinese: '我努力保持健康的生活方式。' },
              { id: 3, russian: 'По утра́м я де́лаю заря́дку.', chinese: '我早上做操。' },
              { id: 4, russian: 'Врач посове́товал мне бо́льше отдыха́ть.', chinese: '医生建议我多休息。' },
              { id: 5, russian: 'Я бро́сил кури́ть год наза́д.', chinese: '我一年前戒烟了。' },
              { id: 6, russian: 'Ну́жно пить бо́льше воды́.', chinese: '需要多喝水。' },
              { id: 7, russian: 'Регуля́рные заня́тия спо́ртом поле́зны.', chinese: '经常运动有益。' },
              { id: 8, russian: 'Я пло́хо сплю́ в после́днее вре́мя.', chinese: '我最近睡眠不好。' },
              { id: 9, russian: 'Мне ну́жно сбро́сить не́сколько килогра́ммов.', chinese: '我需要减几公斤。' },
              { id: 10, russian: 'Пита́ние до́лжно быть сбаланси́рованным.', chinese: '饮食应该均衡。' },
              { id: 11, russian: 'Стресс отрица́тельно влия́ет на здоро́вье.', chinese: '压力对健康有负面影响。' },
              { id: 12, russian: 'Я хожу́ в спортза́л три ра́за в неде́лю.', chinese: '我每周去三次健身房。' },
              { id: 13, russian: 'Она́ соблюда́ет дие́ту.', chinese: '她在节食。' },
              { id: 14, russian: 'Све́жий во́здух о́чень ва́жен.', chinese: '新鲜空气很重要。' },
              { id: 15, russian: 'Я чу́вствую себя́ гора́здо лу́чше.', chinese: '我感觉好多了。' }
            ]
          }
        ]
      }
    ]
  },
  B2: {
    collections: [
      {
        id: 'b2_society',
        name: '俄语高级：社会议题',
        description: '讨论社会、科技、文化等抽象议题，掌握复杂句式和书面表达。',
        videos: [
          {
            id: 'b2_society_01',
            title: '社会议题：科技改变生活',
            description: '用俄语讨论技术进步、文化保护与社会发展等抽象议题。',
            thumbnail: 'https://picsum.photos/seed/ru_society_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_society_01/1280/720',
            level: 'B2',
            duration: '8:40',
            words: 240,
            tags: ['社会', '科技', '高级'],
            learners: 32,
            sentences: [
              { id: 1, russian: 'Совреме́нное о́бщество ста́лкивается с мно́гими пробле́мами.', chinese: '现代社会面临许多问题。' },
              { id: 2, russian: 'Технологи́ческий прогре́сс меня́ет наш о́браз жи́зни.', chinese: '技术进步改变着我们的生活方式。' },
              { id: 3, russian: 'Ва́жно сохраня́ть культу́рное насле́дие.', chinese: '保护文化遗产很重要。' },
              { id: 4, russian: 'Э́та пробле́ма тре́бует серьёзного подхо́да.', chinese: '这个问题需要认真的态度。' },
              { id: 5, russian: 'Мне́ния по э́тому вопро́су раздели́лись.', chinese: '在这个问题上的意见出现了分歧。' },
              { id: 6, russian: 'Необходи́мо найти́ компроми́сс.', chinese: '必须找到折中方案。' },
              { id: 7, russian: 'Э́то явле́ние име́ет глубо́кие ко́рни.', chinese: '这种现象有深刻的根源。' },
              { id: 8, russian: 'Сле́дует обрати́ть внима́ние на э́ти фа́кты.', chinese: '应当注意这些事实。' },
              { id: 9, russian: 'Пра́вительство приня́ло но́вые ме́ры.', chinese: '政府采取了新措施。' },
              { id: 10, russian: 'Учёные провели́ обши́рное иссле́дование.', chinese: '科学家进行了广泛的研究。' },
              { id: 11, russian: 'Результа́ты иссле́дования впечатля́ют.', chinese: '研究结果令人印象深刻。' },
              { id: 12, russian: 'Э́то спосо́бствует разви́тию о́бщества.', chinese: '这有助于社会的发展。' },
              { id: 13, russian: 'Мы до́лжны бере́жно относи́ться к приро́де.', chinese: '我们应该爱护自然。' },
              { id: 14, russian: 'Э́та те́ма вызыва́ет мно́го спо́ров.', chinese: '这个话题引发许多争论。' },
              { id: 15, russian: 'Бу́дущее зави́сит от на́ших реше́ний.', chinese: '未来取决于我们的决定。' }
            ]
          }
        ]
      },
      {
        id: 'b2_tech',
        name: '俄语高级：科技与创新',
        description: '讨论科技发展、人工智能与数字化，掌握抽象论述与书面表达。',
        videos: [
          {
            id: 'b2_tech_01',
            title: '科技前沿：人工智能改变生活',
            description: '用俄语讨论技术进步、创新与社会影响等抽象议题。',
            thumbnail: 'https://picsum.photos/seed/ru_tech_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_tech_01/1280/720',
            level: 'B2',
            duration: '8:20',
            words: 230,
            tags: ['科技', '创新', '高级'],
            learners: 35,
            sentences: [
              { id: 1, russian: 'Техноло́гии развива́ются стреми́тельно.', chinese: '技术发展迅速。' },
              { id: 2, russian: 'Иску́сственный интелле́кт меня́ет мир.', chinese: '人工智能正在改变世界。' },
              { id: 3, russian: 'Смартфо́ны ста́ли ча́стью на́шей жи́зни.', chinese: '智能手机已成为我们生活的一部分。' },
              { id: 4, russian: 'Интерне́т откры́л но́вые возмо́жности для образова́ния.', chinese: '互联网为教育开辟了新可能。' },
              { id: 5, russian: 'Э́то откры́тие име́ет огро́мное значе́ние.', chinese: '这项发现意义重大。' },
              { id: 6, russian: 'Учёные разрабо́тали но́вый материа́л.', chinese: '科学家研发了一种新材料。' },
              { id: 7, russian: 'Цифровиза́ция затра́гивает все сфе́ры.', chinese: '数字化影响所有领域。' },
              { id: 8, russian: 'Мы должны́ защища́ть ли́чные да́нные.', chinese: '我们必须保护个人数据。' },
              { id: 9, russian: 'Робо́ты постепе́нно заменя́ют люде́й на произво́дстве.', chinese: '机器人正在生产中逐步取代人类。' },
              { id: 10, russian: 'Иннова́ции спосо́бствуют экономи́ческому ро́сту.', chinese: '创新促进经济增长。' },
              { id: 11, russian: 'Э́та техноло́гия ещё несоверше́нна.', chinese: '这项技术还不完善。' },
              { id: 12, russian: 'Онла́йн-образова́ние ста́ло популя́рным.', chinese: '在线教育已经流行。' },
              { id: 13, russian: 'Ну́жно осторо́жно относи́ться к но́вым те́хнологиям.', chinese: '需要谨慎对待新技术。' },
              { id: 14, russian: 'Бу́дущее невозмо́жно предста́вить без те́хнологий.', chinese: '未来无法想象没有技术。' },
              { id: 15, russian: 'Мне́ния о влия́нии те́хнологий раздели́лись.', chinese: '关于技术影响的意见存在分歧。' }
            ]
          }
        ]
      },
      {
        id: 'b2_environment',
        name: '俄语高级：环境与自然',
        description: '讨论环境保护、气候变化与可持续发展，练习复杂从句与论述。',
        videos: [
          {
            id: 'b2_environment_01',
            title: '环境保护：我们的共同责任',
            description: '用俄语讨论气候变化、污染治理与生态保护等议题。',
            thumbnail: 'https://picsum.photos/seed/ru_env_01/400/280',
            posterUrl: 'https://picsum.photos/seed/ru_env_01/1280/720',
            level: 'B2',
            duration: '8:40',
            words: 240,
            tags: ['环境', '自然', '高级'],
            learners: 30,
            sentences: [
              { id: 1, russian: 'Защи́та окружа́ющей среды́ — на́ша о́бщая зада́ча.', chinese: '保护环境是我们共同的任务。' },
              { id: 2, russian: 'Глоба́льное потепле́ние вызыва́ет серьёзные опасе́ния.', chinese: '全球变暖引起严重担忧。' },
              { id: 3, russian: 'Мы до́лжны сокраща́ть вы́бросы углеки́слого га́за.', chinese: '我们必须减少二氧化碳排放。' },
              { id: 4, russian: 'Перерабо́тка отхо́дов помога́ет сохраня́ть приро́ду.', chinese: '回收垃圾有助于保护自然。' },
              { id: 5, russian: 'Возобновля́емая эне́ргия стано́вится всё популя́рнее.', chinese: '可再生能源越来越受欢迎。' },
              { id: 6, russian: 'Мно́гие ви́ды живо́тных нахо́дятся под угро́зой исчезнове́ния.', chinese: '许多动物物种濒临灭绝。' },
              { id: 7, russian: 'Загрязне́ние во́здуха вре́дно для здоро́вья.', chinese: '空气污染有害健康。' },
              { id: 8, russian: 'Мы должны́ бере́чь приро́дные ресу́рсы.', chinese: '我们应该珍惜自然资源。' },
              { id: 9, russian: 'Ка́ждый мо́жет внести́ свой вклад.', chinese: '每个人都能做出贡献。' },
              { id: 10, russian: 'Э́та пробле́ма тре́бует междунаро́дного сотру́дничества.', chinese: '这个问题需要国际合作。' },
              { id: 11, russian: 'Сохране́ние лесо́в име́ет ключево́е значе́ние.', chinese: '保护森林至关重要。' },
              { id: 12, russian: 'Мы испо́льзуем сли́шком мно́го пла́стика.', chinese: '我们使用太多塑料。' },
              { id: 13, russian: 'Кли́мат меня́ется бы́стрее, чем ожида́лось.', chinese: '气候变化比预期的更快。' },
              { id: 14, russian: 'Э́ти ме́ры помогу́т улучши́ть ситуа́цию.', chinese: '这些措施将有助于改善情况。' },
              { id: 15, russian: 'Бу́дущее плане́ты в на́ших рука́х.', chinese: '地球的未来在我们手中。' }
            ]
          }
        ]
      }
    ]
  }
}

export function findVideo(videoId) {
  for (const level of LEVELS) {
    for (const collection of courseLibrary[level].collections) {
      const video = collection.videos.find(v => v.id === videoId)
      if (video) return { video, collection, level }
    }
  }
  return null
}

export function getLevelVideos(level) {
  const out = []
  for (const collection of (courseLibrary[level] || {}).collections || []) {
    for (const video of collection.videos) out.push({ video, collection })
  }
  return out
}

export function flatVideoList() {
  const out = []
  for (const level of LEVELS) {
    for (const collection of courseLibrary[level].collections) {
      for (const video of collection.videos) out.push({ video, collection, level })
    }
  }
  return out
}
