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
