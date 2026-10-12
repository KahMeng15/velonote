import { useState, useEffect, useMemo } from 'react';
import {
  Title,
  Text,
  SimpleGrid,
  Card,
  Group,
  ThemeIcon,
  UnstyledButton,
  Box,
  Modal,
  TextInput,
  Textarea,
  ColorInput,
  Button,
  Stack,
  Loader,
  Center,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconCheck,
  IconTrendingUp,
  IconClock,
  IconMessageCircle,
  IconUpload,
  IconBooks,
  IconMessageDots,
  IconFileText,
  IconBrain,
  IconNotes,
} from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { fetchApi } from '../lib/api';

const motivationalMessages = [
  "Let's continue your learning journey",
  "Time to feed your brain some knowledge",
  "Your future self is already smarter because of today",
  "Another day, another neuron connection",
  "Learning mode: activated",
  "Brains are like parachutes — they work best when open",
  "You don't have to be great to start, but you have to start to be great",
  "The expert in anything was once a beginner",
  "Study like you'll live forever",
  "Your brain called — it wants more notes",
  "Success is the sum of small efforts repeated day after day",
  "The more you learn, the more you earn",
  "Knowledge is power — don't keep it waiting",
  "You're one note away from understanding it all",
  "Let's make those brain cells earn their keep",
  "Education is the most powerful weapon you can use",
  "The beautiful thing about learning is nobody can take it away from you",
  "Study now, be a genius later — simple maths",
  "Your only competition is yesterday's you",
  "Learning: the one addiction that's actually good for you",
  "Every master was once a disaster at it",
  "The mind is not a vessel to be filled but a fire to be kindled",
  "You're not stuck, you're just early in the process",
  "The best time to study was yesterday. The next best time is now",
  "In a world where you can be anything, be a lifelong learner",
  "Your brain is hungry — feed it some notes",
  "Procrastinate later. Study now",
  "The harder you work, the luckier you get",
  "Progress, not perfection",
  "You've got this — and if you don't yet, you will",
  "Learning is the only thing that multiplies when shared",
  "The staircase of success is built step by step — or note by note",
  "Wake up, hit the books, conquer the world",
  "Small steps lead to big results",
  "You're building your future self right now",
  "The secret to getting ahead is getting started",
  "Don't watch the clock; do what it does. Keep going",
  "Your grades don't define you, but your effort does",
  "Strive for progress, not perfection",
  "It does not matter how slowly you go as long as you do not stop",
  "The only person you are destined to become is the person you decide to be",
  "Nothing worth having comes easy",
  "Discipline is choosing between what you want now and what you want most",
  "The difference between ordinary and extraordinary is that little extra",
  "Success is not final, failure is not fatal — it's the courage to continue that counts",
  "Believe you can and you're halfway there",
  "Action is the foundational key to all success",
  "The future belongs to those who prepare for it today",
  "An investment in knowledge pays the best interest",
  "Learning never exhausts the mind",
  "The capacity to learn is a gift; the ability to learn is a skill; the willingness to learn is a choice",
  "Study hard, dream big",
  "Your brain is a muscle — time to work it out",
  "Let's turn confusion into clarity, one note at a time",
  "The more you know, the more you realize how much you don't know — and that's beautiful",
  "Today's study session is tomorrow's success story",
  "Be a student as long as you still have something to learn",
  "The beautiful thing about learning is that no one can take it away from you",
  "Education is not preparation for life; education is life itself",
  "Curiosity is the wick in the candle of learning",
  "The mind once stretched by a new idea never returns to its original dimensions",
  "First forget inspiration. Habit is more dependable",
  "Success is no accident. It is hard work, perseverance, learning, studying, sacrifice",
  "The only way to do great work is to love what you do",
  "If you are not willing to learn, no one can help you. If you are determined to learn, no one can stop you",
  "Learning is a treasure that will follow its owner everywhere",
  "Tell me and I forget. Teach me and I remember. Involve me and I learn",
  "The root of education is bitter, but the fruit is sweet",
  "It's what you learn after you know it all that counts",
  "Study while others are sleeping; work while others are loafing",
  "The expert was once a beginner who never gave up",
  "Learning is the beginning of wealth. Learning is the beginning of health. Learning is the beginning of spirituality",
  "You can never be overdressed or overeducated",
  "A little learning is a dangerous thing, but a lot is awesome",
  "I am still learning — and so should you",
  "The pen is mightier than the sword, and notes are mightier than both",
  "Your notes are your superpowers in disguise",
  "Today a reader, tomorrow a leader",
  "Read, study, conquer",
  "Turn your 'I don't get it' into 'I got this'",
  "You didn't come this far to only come this far",
  "Champions keep playing until they get it right",
  "Your only limit is the size of your study session",
  "Let's make those notes work for you",
  "The best way to predict the future is to create it — one study session at a time",
  "Fall in love with learning",
  "Doubt kills more dreams than failure ever will",
  "It's not about having time, it's about making time",
  "The secret of getting ahead is getting started — so let's get started",
  "Your brain is a beautiful thing — let's give it something to think about",
  "Knowledge grows when shared — take some notes",
  "Every note you take is a step toward mastery",
  "You're not just studying, you're building your empire",
  "The student who asks questions is not ignorant, but curious",
  "Let's turn those complex topics into simple notes",
  "Your dedication today is your achievement tomorrow",
  "Learn something new every day — or at least review something old",
  "You can't go back and change the beginning, but you can start where you are and change the ending",
  "Turn your 'someday' into 'today'",
  "Learning is the gateway to everything you want in life",
  "The best investment you can make is in yourself",
  "Be kind to your mind — feed it knowledge",
  "Great things never come from comfort zones",
  "Your notes collection is your personal treasure chest",
  "The study grind doesn't stop — and neither do you",
  "Today's notes are tomorrow's A+",
  "Study smarter, not just harder",
  "Clarity comes from engagement, not from thinking about it",
  "Your future is written in the notes you take today",
  "The exam doesn't care if you're tired — but your notes do",
  "Notes are the WiFi between your ears and your grades",
  "Your brain deserves a better screensaver — time to study",
  "Be the reason your GPA smiles",
  "May the force be with your study session",
  "You + Notes = Unstoppable",
  "Don't stop when you're tired. Stop when you're done",
  "Make your notes so good that future you sends a thank-you note",
  "Your notes are basically a love letter to your future self",
  "Study like there's no exam — but there is, so actually study",
  "Cramming is just speed-running knowledge",
  "If studying is wrong, I don't wanna be right — wait, no, that's not right",
  "Your notes called, they said 'study me'",
  "The early bird gets the worm, but the second mouse gets the cheese — just study already",
  "Study is just adulting for your brain",
  "One does not simply 'wing it' — take notes",
  "Your brain on notes: still beautiful",
  "In this house, we study and we know things",
  "Let's get this bread — study edition",
  "No notes, no glory",
  "The grind is real, but so are your notes",
  "Sleep is for the weak — said no smart person ever. Study well, rest well",
  "Notes: because remembering things is overrated",
  "You're not procrastinating, you're just pre-studying for later",
  "The library called, it misses you",
  "Your textbooks are gathering dust. Let's fix that",
  "Break a leg — unless you're studying anatomy, in which case know the name of that bone",
  "Ctrl+S your brain — take notes",
  "2 + 2 = study",
  "Knowledge is knowing a tomato is a fruit. Wisdom is not putting it in a fruit salad",
  "That voice saying 'you should study'? Listen to it. It's smart",
  "Here for a good time AND a smart time",
  "You can lead a horse to water, but you can't make it think — wait, you can with notes",
  "I'm not saying you're a genius, but you're definitely on the right track",
  "Sending good study vibes your way",
  "Let's turn that 'idk' into 'I know'",
  "The more you study, the fewer things you'll have to Google at 2 AM",
  "Your GPA called — it wants more notes",
  "The treasure you seek is hidden in your study materials",
  "Learning is the shiny Pokémon of life — gotta catch 'em all",
  "Failing to prepare is preparing to fail — so prepare with notes",
  "Einstein didn't wing it. Neither should you",
  "This is your brain. This is your brain on notes. Any questions?",
  "You're doing great, sweetie — now study",
  "Our notes, our future",
  "Just keep studying, just keep studying",
  "Under the sea? No, under the books",
  "I'll study when I'm dead — but for now, let's get it done",
  "Let's build that knowledge muscle",
  "Absorb knowledge like a sponge that's really into self-improvement",
  "Every study session is a tiny step toward world domination",
  "You're not studying — you're upgrading your firmware",
  "Reading is dreaming with your eyes open",
  "Notes are the GPS to your academic success",
  "You're not behind, you're just on a different page — literally, open the book",
  "Life is short — study fast",
  "The best things in life are free. Knowledge is free. So study",
  "You are the author of your own success story — start with this chapter",
  "The study session is calling and I must go",
  "Hakuna Matata — it means no worries, unless you haven't studied",
  "Be like a shark. Keep moving forward. Keep studying.",
  "Wingardium Studiosa!",
  "Live long and prosper — and study",
  "Resistance is futile. You will be assimilated into knowledge",
  "This is the way — of studying",
  "Winter is coming — and so are exams",
  "You know nothing, Jon Snow — but not for long",
  "With great power comes great responsibility — and great notes",
  "To infinity and beyond — your study potential",
  "Just do it — study",
  "Impossible is nothing — when you have notes",
  "Believe in the me that believes in you — and also in your notes",
  "Plus ultra — go beyond, plus study",
  "I'll take 'Things I Should Be Doing' for 500, Alex",
  "This is fine. Everything is fine. I have my notes.",
  "The study struggle is real, but so is your progress",
  "Your brain before coffee is not a valid excuse",
  "Future you is counting on current you — don't let them down",
  "You are the main character of your academic journey — act like it",
  "Insert coin to continue studying",
  "Level up: Study Session Initiated",
  "New achievement unlocked: Opened the app",
  "Side quest: Understand one new concept today",
  "Boss battle: That one topic you keep avoiding",
  "You have entered the study zone",
  "Loading knowledge... 100% complete",
  "Day [current] of becoming a knowledge wizard",
  "Your study streak is glowing",
  "Keep calm and carry notes",
  "Adopt the pace of nature — her secret is patience, and study",
  "It is not the mountain we conquer but ourselves — and our study materials",
  "The only Zen you'll find on this app is the Zen of studying",
  "Simplicity is the ultimate sophistication — and clear notes are simple",
  "Art is never finished, only abandoned — same with studying, so keep going",
  "If you can't explain it simply, you don't understand it well enough — make better notes",
  "To study is to live twice",
  "The purpose of learning is growth, and our minds, unlike our bodies, can continue growing",
  "Happiness is not in the mere possession of knowledge; it is in the act of acquiring it",
  "When you study, you are not filling a bucket, but lighting a fire",
  "I have no special talent. I am only passionately curious. And I take notes.",
  "The important thing is not to stop questioning — or note-taking",
  "Learn from yesterday, live for today, study for tomorrow",
  "Time you enjoy wasting was not wasted — unless you should have been studying",
  "Wisdom is not a product of schooling but of the lifelong attempt to acquire it",
  "The only true wisdom is in knowing you know nothing — so study to know something",
  "You can't study calculus in a day, but you can start",
  "Small progress is still progress",
  "Your brain is not a search engine — make sure you index it with notes",
  "Some people want it to happen, some wish it would happen, others make it happen — studiers",
  "A year from now you will wish you had started today — so start now",
  "The secret to success is to start from scratch and keep going",
  "Twenty years from now you'll be more disappointed by the things you didn't study than the ones you did",
  "The best time to plant a tree was 20 years ago. The second best time is now — same for studying",
  "You don't need to see the whole staircase, just take the first study step",
  "Your notes are not heavy — they're your brothers, sisters, and parents in knowledge",
  "Study is what makes the world go round",
  "I think, therefore I study",
  "In the middle of difficulty lies opportunity — and notes",
  "Life is what happens when you're busy studying — and that's a good thing",
  "Carpe diem — seize the study session",
  "Fortune favors the bold — and the studious",
  "A journey of a thousand miles begins with a single note",
  "Veni, vidi, studui — I came, I saw, I studied",
  "Cogito ergo sum — I think, therefore I study",
  "Ad astra per aspera — through hardships to the stars, and through study to success",
  "Carpe noctem — seize the night study session",
  "Dum spiro, spero — while I breathe, I hope and study",
  "Vincit qui se vincit — he conquers who conquers himself and his study habits",
  "Audentes fortuna iuvat — fortune favors the studious",
  "Acta non verba — actions, not words — study, don't just talk about it",
  "If you think education is expensive, try ignorance — so take notes",
  "The door to knowledge is open — walk through it",
  "Your diploma is just a piece of paper. Your knowledge is forever.",
  "Grades measure performance, not potential — but both improve with study",
  "You're not just studying for a test; you're studying for life",
  "The most expensive thing you can buy is ignorance — avoid it with notes",
  "College is expensive. Notes are cheap. Do the math.",
  "A degree doesn't make you smart. Studying makes you smart.",
  "The student loan is real. The knowledge is realer. Make it count.",
  "If knowledge is power, then notes are your power-up",
  "Not all heroes wear capes — some take notes",
  "Behind every successful student is a mountain of notes",
  "Your notes are your secret weapon",
  "Legend has it: the best students are the ones who take the best notes",
  "In a world full of distractions, be a note-taker",
  "The notebook of life is written one page at a time",
  "Swipe right on knowledge — start studying",
  "Your daily dose of brain food is ready",
  "The algorithm of success: study + notes = results",
  "Optimize your brain's database with regular study sessions",
  "Running low on knowledge — time for a refill",
  "Notifications: your future self wants you to study",
  "You have 99 problems but studying can fix at least half of them",
  "Error 404: knowledge not found. Please insert notes",
  "Access denied: ignorance detected. Study required",
  "The system detected a knowledge gap. Patching with study session.",
  "Your brain's storage is 10% full. Time to fill it up.",
  "Your memory has been upgraded. Notes required for activation.",
  "Knowledge packets incoming — open your brain's WiFi",
  "This is your captain speaking: please fasten your study materials",
  "Flight to Knowledgeville now boarding at gate Notes",
  "Destination: Success. Layover: Study Session",
  "Keep your tray tables up and your notes open",
  "Your study session has been confirmed. Enjoy the flight.",
  "All aboard the knowledge train — next stop: understanding",
  "The wheels on the bus go round and round — and so do study sessions",
  "Now arriving at: Station of Comprehension",
  "Please mind the gap between ignorance and knowledge — fill it with notes",
  "The knowledge express is leaving the station — all aboard",
  "Fuel your brain, conquer the day",
  "Breakfast of champions: coffee and notes",
  "Eat, sleep, study, repeat",
  "Your brain needs premium fuel — feed it knowledge",
  "A balanced diet is a note in each hand",
  "An apple a day keeps the doctor away, but notes keep the F away",
  "Procrastination is the thief of time — arrest it with a study session",
  "The early bird gets the worm, but the studious bird gets the A",
  "Let's make this a productive procrastination session",
  "You can sleep when you're dead — but you can study now",
  "Time flies when you're studying — wait, does it?",
  "A stitch in time saves nine — and a note in time saves cramming",
  "Better late than never, but never late is better — for studying",
  "Practice what you study",
  "If at first you don't succeed, study again",
  "Absence makes the heart grow fonder — and grades grow lower. So don't be absent from studying",
  "The squeaky wheel gets the grease — and the noisy studier gets the knowledge",
  "When life gives you lemons, make lemonade — and study for the quiz",
  "Don't count your chickens before they hatch — count your notes instead",
  "A watched pot never boils — but a watched study session does wonders",
  "Don't put all your eggs in one basket — spread your study sessions out",
  "Kill two birds with one stone — study one topic that relates to another",
  "Let sleeping dogs lie — but wake up your brain and study",
  "The ball is in your court — serve with a study session",
  "You can't make an omelette without breaking eggs — or studying",
  "Rome wasn't built in a day — but it was studied into existence",
  "Smooth seas do not make skillful sailors — and easy topics don't make sharp minds",
  "The only way out is through — study your way to understanding",
  "Patience is bitter, but its fruit is sweet — like studying for a tough exam",
  "You reap what you sow — sow notes, reap knowledge",
  "The early bird catches the worm — but the night owl gets the study done too",
  "Don't bite off more than you can chew — but do chew on some notes",
  "Birds of a feather study together",
  "When the cat's away, the mice will study — okay, maybe not",
  "Curiosity killed the cat, but satisfaction brought it back — curiosity drives learning",
  "A rolling stone gathers no moss — and a studying mind gathers knowledge",
  "Every cloud has a silver lining — your study session is that lining",
  "The pen is mightier than the sword — and notes are mightier than cramming",
  "Actions speak louder than words — and study sessions speak volumes",
  "All that glitters is not gold — but knowledge is worth more than gold",
  "Beauty is in the eye of the beholder — and knowledge is in the eye of the studier",
  "Beggars can't be choosers — but students can choose to study",
  "The best things in life are free — and studying is basically free",
  "Cleanliness is next to godliness — and clear notes are next to genius",
  "A friend in need is a friend indeed — your notes are your best friend",
  "Half a loaf is better than none — half a study session is better than nothing",
  "Honesty is the best policy — and honestly, you need to study more",
  "Ignorance is bliss — but knowledge is better, so study",
  "It's never too late to mend — or to start studying",
  "Keep your friends close and your notes closer",
  "Laughter is the best medicine — but studying prevents the disease of ignorance",
  "Look before you leap — and study before you test",
  "Make hay while the sun shines — and study while your brain is fresh",
  "Necessity is the mother of invention — and studying is the father of understanding",
  "No man is an island — but every student needs their notes",
  "Nothing ventured, nothing gained — venture into your study materials",
  "Once bitten, twice shy — once failed, twice the study effort",
  "Out of sight, out of mind — so keep your notes visible",
  "Practice makes perfect — studying makes progress",
  "Pride comes before a fall — humility comes before learning",
  "Slow and steady wins the race — consistent studying over cramming",
  "Strike while the iron is hot — study while the topic is fresh",
  "The grass is always greener on the other side — where they study more",
  "Too many cooks spoil the broth — but too many notes spoil... nothing. Take more notes.",
  "Two heads are better than one — study groups for the win",
  "Where there's a will, there's a way — and there's always a way to study",
  "You can catch more flies with honey than vinegar — but you can catch As with notes",
  "You can lead a horse to water, but you can't make it drink — you CAN make it study though",
  "Your future self will thank you for studying today",
  "One day you'll look back and be glad you didn't skip this study session",
  "The exam is temporary. The knowledge is forever.",
  "Your notes are a time capsule for your future self",
  "Someone out there is studying harder than you. Make sure it's not too many people",
  "The library is calling. Will you answer the call?",
  "Your desk is waiting. The chair is ready. The notes are prepared.",
  "The only thing standing between you and success is a study session",
  "Unlock your potential — one note at a time",
  "The key to success is hidden in your study materials",
  "Your education is a dress rehearsal for a life that is yours to shape",
  "Every expert was once a beginner who took notes",
  "Behind every great mind is a pile of great notes",
  "Your notes today are the foundation of your wisdom tomorrow",
  "The best time to start studying was yesterday. The next best time is literally right now",
  "Read, learn, grow — the cycle never ends",
  "Every minute spent studying is an investment in your future self",
  "Your brain is the most powerful computer — don't forget to update it with new knowledge",
  "The only app you need to open today is your brain — and maybe this one",
  "Don't let your dreams be dreams — let them be study sessions",
  "Success starts with a single step — or a single note",
  "The more you study, the more interesting everything becomes",
  "You are the artist of your own education — paint with notes",
  "Your notes are the blueprint to your academic success",
  "The universe is made of stories, not atoms — and your study story starts now",
  "Be the protagonist of your own learning journey",
  "There are no shortcuts to any place worth going — except through study notes",
  "The road to success is dotted with many tempting parking spaces — keep driving",
  "Don't wait for the perfect moment. Take the moment and make it perfect — with study",
  "Your only limit is the amount of knowledge you haven't absorbed yet",
  "Begin anywhere — but just begin studying",
  "The starting point of all achievement is desire — and a good set of notes",
  "You miss 100% of the shots you don't take — and 100% of the concepts you don't study",
  "Champions don't show up to get everything right. They show up to get better — just like studying",
  "Hard work beats talent when talent doesn't work hard — so study hard",
  "It's not about being the best. It's about being better than you were yesterday",
  "Success is not about how fast you go, but that you never stop — especially studying",
  "Your study habits today shape your success tomorrow",
  "The only way to do great work is to love what you study",
  "Don't be afraid to study hard. Be afraid of the regret of not trying",
  "What you get by achieving your goals is not as important as what you become by achieving them — a studier",
  "You are braver than you believe, stronger than you seem, and smarter than you study",
  "The future starts today, not tomorrow — open your notes",
  "You don't have to be extreme, just consistent — with your study sessions",
  "Every study session adds another brick to your foundation of knowledge",
  "Your notes are a mirror of your determination",
  "Let your studying be so good that your past self would be proud",
  "The only person who can stop you from learning is you — don't be that person",
  "Turn your 'I wish I knew' into 'I know this'",
  "Knowledge isn't free. You have to pay attention — and take notes",
  "Study is the paintbrush that colors your future",
  "Your brain is a garden. Notes are the water. Grow something beautiful.",
  "Be a knowledge hoarder — collect notes like treasure",
  "In the game of life, knowledge is the ultimate power-up",
  "Level up your brain with every study session",
  "Life is a puzzle. Notes are the pieces. Put them together.",
  "Every note is a stepping stone on the path to mastery",
  "Don't just read — absorb. Don't just listen — understand. Take notes.",
  "The best students aren't the smartest. They're the ones who never stop taking notes.",
  "Your notes today are the answers to tomorrow's questions",
  "The secret to success is no secret — it's just consistent study",
  "You can do anything, but not everything — so focus on what matters and study it",
  "The expert at anything was once a beginner who didn't give up on their notes",
  "Your potential is infinite. Your study time is not. Make it count.",
  "The student who says 'I can't' is right. The one who says 'I'll study' is right too.",
  "Your brain is like a muscle. Notes are the workout. Get those gains.",
  "It's not about having time. It's about making time to study.",
  "You're capable of amazing things — starting with this study session",
  "Don't let fear of failure stop you from studying. Let fear of failure motivate you.",
  "Every moment spent studying is a moment your future self thanks you for",
  "You are the CEO of your own education — start acting like it",
  "Your notes are not just text on a page. They're the blueprint of your success.",
  "Be so focused on studying that you don't have time to procrastinate",
  "The only competition that matters is who you were yesterday — make them proud by studying",
  "Today is a great day to learn something new and take notes about it",
  "Don't study to pass. Study to understand. Then passing becomes easy.",
  "Your education is a gift. Notes are the wrapping paper. Unwrap it every day.",
  "The answer you're looking for is probably in your notes — or will be after this session",
  "You don't need motivation. You need discipline. Open your notes.",
  "Reading without taking notes is like eating without tasting — you miss the best part",
  "Your brain on notes is a beautiful thing",
  "There is no wifi in the forest, but there's knowledge in your notes",
  "The best project you'll ever work on is yourself — study accordingly",
  "Don't count the minutes studying. Make the minutes studying count.",
  "Your grades are a reflection of your study habits. Time to polish them.",
  "The world is full of things to learn — grab your notes and dive in",
  "Every great achievement starts with the decision to try — and take notes",
  "You are the architect of your knowledge — build with notes",
  "The mind is like a sponge. Make sure yours is soaked in knowledge.",
  "Studying is not a chore. It's a choice. Choose wisely.",
  "Your future self has big dreams — help them out with today's study session",
  "One note at a time. One concept at a time. One success at a time.",
  "The path to mastery is paved with good notes",
  "Your brain deserves the best fuel — feed it knowledge daily",
  "The only way to learn is to do — and notes help you remember what you did",
  "Start where you are. Use what you have. Study what you can.",
  "Don't wish for it. Work for it. With notes.",
  "The secret to getting ahead is getting started — so start studying",
  "Your future is created by what you do today — not tomorrow. Study now.",
  "Be a lifelong learner. Your notes will thank you.",
  "Success is not about being the best — it's about being better than you were",
  "Let's turn that confusion into understanding, one note at a time",
  "Time to make your ancestors proud by studying hard",
  "Your notes are your legacy — make them count",
  "The ultimate life hack is studying — it works every time",
  "You can't build a reputation on what you're going to study — so study now",
  "The biggest risk is not taking any study session at all",
  "Your only obligation in life is to be true to yourself — and to your study schedule",
  "The purpose of life is not to be happy. It is to be useful, honorable, compassionate — and well-studied",
  "Life is really simple, but we insist on making it complicated — so simplify with clear notes",
  "The only source of knowledge is experience — and notes about that experience",
  "The measure of intelligence is the ability to change — and study enables that change",
  "The good life is one inspired by love and guided by knowledge — study both",
  "It is not that I'm so smart. It's that I stay with questions longer — and take notes",
  "The mind that opens to a new idea never returns to its original size — or its original ignorance",
  "When you change the way you look at studying, the thing you study changes",
  "The art of being wise is the art of knowing what to overlook — but not what to avoid studying",
  "Creativity is intelligence having fun — and notes are intelligence working",
  "The intuitive mind is a sacred gift and the rational mind is a faithful servant — study to balance both",
  "Learn the rules like a pro so you can break them like an artist — but first, take notes",
  "The most beautiful thing we can experience is the mysterious — and the mystery of learning",
  "Imagination is more important than knowledge — but knowledge fuels imagination. Study both.",
  "Try not to become a man of success, but rather try to become a man of value — and value comes from learning",
  "The important thing is not to stop questioning — or note-taking",
  "Anyone who has never made a mistake has never tried anything new — or studied hard enough",
  "Insanity is doing the same thing over and over and expecting different results — so study differently",
  "I have not failed. I've just found 10,000 ways that won't work — and I took notes on each one",
  "Strive not to be a success, but rather to be of value — and studying adds value",
  "The best revenge is massive success — fueled by massive knowledge",
  "Life is 10% what happens to us and 90% how we react to it — study to react better",
  "The wise speak because they have something to say; fools because they have to say something — study to have something worth saying",
  "Knowledge is knowing what to say. Wisdom is knowing when to say it. Notes help with both.",
  "Common sense is not common — but studying makes it more common",
  "The greatest enemy of knowledge is not ignorance, it is the illusion of knowledge — take notes to stay grounded",
  "A smart person learns from their mistakes. A wise person learns from others' mistakes. A note-taker learns from both.",
  "The mediocre teacher tells. The good teacher explains. The great teacher inspires — and the best student takes notes",
  "The whole purpose of education is to turn mirrors into windows — and notes into understanding",
  "The educated differ from the uneducated as much as the living from the dead — so keep studying",
  "The roots of education are bitter, but the fruit is sweet — keep watering with notes",
  "Education is the passport to the future, for tomorrow belongs to those who prepare for it today",
  "The beautiful thing about learning is that nobody can take it away from you — so collect as much as possible",
  "Develop a passion for learning. If you do, you will never cease to grow.",
  "Learning is like rowing upstream: not to advance is to drop back — so keep paddling with notes",
  "To teach is to learn twice — and to take notes is to learn thrice",
  "The noblest pleasure is the joy of understanding — and the joy of taking great notes",
  "To know is to know that you know nothing. That is the meaning of true knowledge — so study more",
  "The most useful piece of learning for the uses of life is to unlearn what is untrue — and learn what is true with notes",
  "It is what you read when you don't have to that determines what you will be when you can't help it — so study voluntarily",
  "Study is the kindling of a flame, not the filling of a vessel",
  "The mind is not a vessel to be filled but a fire to be kindled — notes are the kindling",
  "Education is not the learning of facts, but the training of the mind to think — notes help that training",
  "The function of education is to teach one to think intensively and to think critically — both require notes",
  "Real knowledge is to know the extent of one's ignorance — and to take notes on it",
  "The only person who is educated is the one who has learned how to learn and change",
  "Education without application is just entertainment — apply what you study with notes",
  "The highest activity a human being can attain is learning for understanding — and taking notes",
  "The pursuit of truth and beauty is a sphere of activity in which we are permitted to remain children all our lives — so keep studying",
  "Learn as if you will live forever, live as if you will die tomorrow — and take notes in between",
  "The more I read, the more I acquire, the more certain I am that I know nothing — so I take notes",
  "The greatest good you can do for another is not just to share your riches but to reveal to them their own — through shared notes",
  "The only thing that interferes with my learning is my education — so I supplement it with notes",
  "The best teachers are those who show you where to look but don't tell you what to see — and give you note-taking skills",
  "The classroom is a window on the world. Keep it clean with clear notes.",
  "The test of a good teacher is not how many questions they can ask, but how many they inspire their students to answer — with notes",
  "Education is not received. It is achieved. Through study and notes.",
  "The journey of a thousand miles begins with a single step — and continues with consistent notes",
  "What we learn with pleasure we never forget — make note-taking pleasurable",
  "The best way to predict your future is to create it — with study sessions and notes",
  "If you think you can or you think you can't, you're right — but either way, notes help",
  "Whether you believe you can or you can't, you're right — so believe in your notes",
  "Your limitation—it's only your imagination — and your imagination is fueled by knowledge from notes",
  "The difference between who you are and who you want to be is what you do — and what you study",
  "Push yourself because no one else is going to do it for you — except your notes, they're always there",
  "Great things never come from comfort zones — they come from study sessions",
  "Dream it. Wish it. Do it. With notes.",
  "Success doesn't just find you. You have to go out and earn it — with study sessions",
  "The harder you work, the luckier you get — and studying is the hardest work",
  "There is no substitute for hard work — or for well-organized notes",
  "The only place where success comes before work is in the dictionary — so study first",
  "Success is not in what you have, but who you are — and who you become through studying",
  "Success usually comes to those who are too busy to be looking for it — like busy studiers",
  "Opportunities don't happen. You create them — with the knowledge from your notes",
  "If you want something you've never had, you must be willing to do something you've never done — like study more",
  "Don't be afraid to give up the good to go for the great — study beyond the syllabus",
  "The key to success is to focus on goals, not obstacles — and notes help you stay focused",
  "The secret of success is to do the common thing uncommonly well — like taking exceptional notes",
  "Success is the sum of small efforts, repeated day-in and day-out — consistent note-taking",
  "The road to success and the road to failure are almost exactly the same — take notes to stay on track",
  "Success is walking from failure to failure with no loss of enthusiasm — and with a good set of notes",
  "I have not failed. I've just found 10,000 ways that won't work — and I have notes on all of them",
  "Your attitude, not your aptitude, will determine your altitude — a good study attitude helps",
  "Motivation is what gets you started. Habit is what keeps you going — and note-taking is a great habit",
  "You don't have to be extreme, just consistent — consistent note-taking leads to success",
  "Success is not about being the best. It's about being better than you were yesterday — by studying today",
  "Be the change that you wish to see in the world — and study to understand what changes are needed",
  "An eye for an eye makes the whole world blind. An eye for knowledge makes the whole world smart.",
  "Injustice anywhere is a threat to justice everywhere — so study to understand and fight injustice",
  "The time is always right to do what is right — and studying is always right",
  "Darkness cannot drive out darkness; only light can do that — and knowledge is light",
  "The ultimate measure of a person is not where they stand in moments of comfort, but where they stand in moments of challenge — and challenge requires study",
  "Our lives begin to end the day we become silent about things that matter — so study to find your voice",
  "Freedom is never voluntarily given by the oppressor; it must be demanded by the oppressed — and knowledge is the key",
  "Nothing in all the world is more dangerous than sincere ignorance and conscientious stupidity — study to stay safe",
  "The function of education is to teach one to think intensively and to think critically. Notes help.",
  "Intelligence plus character — that is the goal of true education. Notes help build both.",
  "We must accept finite disappointment, but never lose infinite hope — or the habit of taking notes",
  "The best way to find yourself is to lose yourself in the service of others — and in the study of useful knowledge",
  "The ultimate tragedy is not the oppression and cruelty by the bad people but the silence over that by the good people — speak up, know more, study",
  "Study is what remains after one has forgotten what one has learned in school",
  "You can never be overdressed or overeducated — overeducation starts with over-note-taking",
  "If history repeats itself, and the unexpected always happens, how incapable must Man be of learning from experience — take notes on history",
  "You can't wait for inspiration. You have to go after it with a club — and a notebook",
  "The moment you feel like you have to study, you should. The moment you feel like you don't, you should anyway.",
  "The trick to studying is not minding that it's hard",
  "You become what you study",
  "The cave you fear to enter holds the treasure you seek — study what scares you",
  "We are what we repeatedly do. Excellence, then, is not an act, but a habit — make studying a habit",
  "Happiness is not something ready made. It comes from your own actions — like studying and taking notes",
  "The only way to make sense out of change is to plunge into it, move with it, and join the dance — and study the steps",
  "Life is not a problem to be solved, but a reality to be experienced — and notes help you remember the experience",
  "What is to give light must endure burning — and studying can feel like burning, but the light is worth it",
  "There is no passion to be found playing small — in settling for a life that is less than the one you are capable of studying for",
  "Your time is limited, don't waste it living someone else's life — or not studying for your own goals",
  "Have the courage to follow your heart and intuition — and the discipline to study what you need",
  "Stay hungry, stay foolish — and keep your notebook full",
  "The only way to be truly satisfied is to do what you believe is great work — and the only way to do great work is to study what you love",
  "Your work is going to fill a large part of your life, and the only way to be truly satisfied is to do what you believe is great work — so study to do great work",
  "Don't let the noise of others' opinions drown out your own inner voice — or your study goals",
  "The greatest glory in living lies not in never falling, but in rising every time we fall — and studying to rise higher",
  "The way to get started is to quit talking and begin studying",
  "Life is what happens when you're busy making other plans — so plan your study sessions",
  "Spread love everywhere you go. Let no one ever come to you without leaving happier — and smarter, from your notes",
  "When you reach the end of your rope, tie a knot in it and hang on — and study while you hang",
  "It is during our darkest moments that we must focus to see the light — and the light often comes from knowledge",
  "The best and most beautiful things in the world cannot be seen or even touched — they must be felt with the heart and understood through study",
  "The sun is a daily reminder that we too can rise from the darkness and shine — and studying helps us rise",
  "Let us always meet each other with smile, for the smile is the beginning of love — and knowledge is the beginning of wisdom",
  "The greatest glory of a free-born people is to transmit that freedom to their children — and the best way is through education and notes",
  "Reading is essential for those who seek to rise above the ordinary — and notes are essential for those who seek to remember what they read",
  "The journey of a lifetime begins with the turning of a page — and the writing of a note",
  "Study now, thank yourself later",
  "You know what's cool? Knowing stuff. Study.",
  "YOLO — You Only Learn Once, so make it count with notes",
  "The vibes are academic",
  "Main character energy requires main character knowledge — study up",
  "It's giving... studious vibes",
  "Slay the day — with notes",
  "The glow-up starts with the show-up — show up to study",
  "No cap, studying is actually based",
  "Rizz up your brain with some knowledge",
  "Bet you can't study for just five minutes — go ahead, try it",
  "It's giving 'I'm going to ace this' energy",
  "Period — as in, period of focused study",
  "Ate and left no crumbs — that's you after this study session",
  "The audacity of people who don't take notes — don't be one of them",
  "Living that note-taking lifestyle",
  "Fr fr, notes are the move",
  "Study session? More like slay session",
  "Touch grass after you study — but study first",
  "On god, your notes are fire",
  "You're him. You're her. You're that studier.",
  "Hot girl/boy summer starts with hot grades — and hot grades need notes",
  "Your brain: let's gooo, another study session",
  "The study game is strong with this one",
  "Flex on 'em with your knowledge",
  "POV: you're about to become unstoppable",
  "It's not a vibe, it's a lifestyle — the note-taking lifestyle",
];

const quickActions = [
  { label: 'Upload', icon: IconUpload, color: 'indigo', path: '/upload' },
  { label: 'My Notes', icon: IconBooks, color: 'teal', path: '/mynotes' },
  { label: 'Chat', icon: IconMessageDots, color: 'blue', path: '/chat' },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const [subjectModalOpened, { open: openSubjectModal, close: closeSubjectModal }] = useDisclosure(false);

  const [summary, setSummary] = useState({
    total_subjects: 0,
    total_notes: 0,
    study_time_7d_mins: 0,
    questions_asked_7d: 0
  });
  
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userName = user.nickname || user.full_name || user.username || 'Student';

  const greetings = [
    `Welcome back, ${userName}`,
    `Hey there, ${userName}`,
    `Ready when you are, ${userName}`,
    `Good to see you, ${userName}`,
    `Let's go, ${userName}`,
    `Back at it, ${userName}`,
    `You're back, ${userName}`,
    `Hello again, ${userName}`,
    `Right on time, ${userName}`,
    `Looking sharp, ${userName}`,
    `The gang's all here, ${userName}`,
    `Eyes up, ${userName}`,
    `Reporting for duty, ${userName}`,
    `Welcome to the grid, ${userName}`,
    `Locked in, ${userName}`,
    `${userName} has entered the study zone`,
    `Now starring: ${userName}`,
    `${userName} mode: activated`,
    `All systems online, ${userName}`,
    `${userName} in the house`,
    `The one and only ${userName}`,
    `Lighting up the room, ${userName}`,
    `Chapter ${userName}: The Studying`,
    `${userName} — the name, the legend`,
    `Special guest appearance: ${userName}`,
    `Is it ${userName}? Yes it is.`,
    `Nobody: ... Absolutely nobody: ... ${userName}: I'm about to study`,
    `Plot twist: ${userName} is back`,
    `Incoming transmission from ${userName}`,
    `${userName} has logged in`,
  ];

  const greeting = useMemo(() => greetings[Math.floor(Math.random() * greetings.length)], []);
  const message = useMemo(() => motivationalMessages[Math.floor(Math.random() * motivationalMessages.length)], []);

  const [recentItems, setRecentItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [summaryData, recentData] = await Promise.all([
          fetchApi('/analytics/dashboard-summary'),
          fetchApi('/search/recent')
        ]);
        setSummary(summaryData);
        setRecentItems(recentData || []);
      } catch (err) {
        console.error("Failed to load dashboard data", err);
      } finally {
        setLoadingItems(false);
      }
    };
    loadData();
  }, []);

  const formatStudyTime = (mins) => {
    if (mins >= 60) {
      return `${Math.floor(mins / 60)}h ${mins % 60}m`;
    }
    return `${mins}m`;
  };

  const stats = [
    { label: 'Total Subjects', value: summary.total_subjects.toString(), delta: 'Active', icon: IconCheck, color: 'teal' },
    { label: 'Total Notes', value: summary.total_notes.toString(), delta: 'Updated', icon: IconTrendingUp, color: 'blue' },
    { label: 'Study Time (7d)', value: formatStudyTime(summary.study_time_7d_mins), delta: 'Focus', icon: IconClock, color: 'grape' },
    { label: 'Questions (7d)', value: summary.questions_asked_7d.toString(), delta: 'Active', icon: IconMessageCircle, color: 'orange' },
  ];

  return (
    <Box pt="lg">
      {/* Welcome Section */}
      <Box mb="xl">
        <Text ff="Instrument Serif, serif" fs="italic" style={{ fontSize: 'clamp(3rem, 5vw, 4rem)', fontWeight: 700, lineHeight: 0.9, color: '#171738', wordBreak: 'break-word' }}>
          {greeting}
        </Text>
        <Text c="dimmed" size={{ base: 'sm', md: 'lg' }} mt={4}>
          {message}
        </Text>
      </Box>

      {/* Quick Stats */}
      <SimpleGrid cols={{ base: 2, md: 4 }} spacing="sm" mb="xl">
        {stats.map((stat) => (
          <Card key={stat.label} withBorder padding="md" radius="md" style={{ minHeight: 110 }}>
            <Stack gap={0} style={{ height: '100%' }}>
              <Group justify="space-between" align="center">
                <Text size="xs" c="dimmed" fw={700} tt="uppercase" truncate style={{ flex: 1 }}>
                  {stat.label}
                </Text>
                <ThemeIcon color={stat.color} variant="light" size={34} radius="md" style={{ flexShrink: 0 }}>
                  <stat.icon size={18} stroke={1.5} />
                </ThemeIcon>
              </Group>
              <Box style={{ flex: 1 }} />
              <Text size="xl" fw={700} lh={1}>
                {stat.value}
              </Text>
              <Text c="teal" size="xs" fw={500} mt={2}>
                {stat.delta}
              </Text>
            </Stack>
          </Card>
        ))}
      </SimpleGrid>

      {/* Quick Actions */}
      <Title order={3} mb="md" fw={600} style={{ fontFamily: 'Instrument Sans, sans-serif', color: '#171738' }}>
        Quick Actions
      </Title>
      <Group gap="lg" mb="xl" style={{ flexWrap: 'nowrap', overflowX: 'auto' }}>
        {quickActions.map((action) => (
          <UnstyledButton
            key={action.label}
            onClick={() => navigate(action.path)}
            style={(theme) => ({
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: theme.spacing.md,
              borderRadius: theme.radius.md,
              backgroundColor: '#fff',
              transition: 'transform 150ms ease, box-shadow 150ms ease',
              border: `1px solid ${theme.colors.gray[2]}`,
              flex: 1,
              minWidth: 80,
              '&:hover': {
                transform: 'translateY(-2px)',
                boxShadow: theme.shadows.sm,
              },
            })}
          >
            <ThemeIcon color={action.color} variant="filled" size={50} radius="xl" mb="sm">
              <action.icon size={26} stroke={1.5} />
            </ThemeIcon>
            <Text size="sm" fw={600} c="#171738">
              {action.label}
            </Text>
          </UnstyledButton>
        ))}
      </Group>

      {/* Recent Items Section */}
      <Title order={3} mb="md" mt="xl" fw={600} style={{ fontFamily: 'Instrument Sans, sans-serif', color: '#171738' }}>Recent Items</Title>
      
      {loadingItems ? (
        <Card withBorder radius="md" padding="xl">
          <Center style={{ height: 150 }}>
            <Stack align="center" spacing="xs">
              <Loader type="bars" />
              <Text c="dimmed">Loading recent items...</Text>
            </Stack>
          </Center>
        </Card>
      ) : recentItems.length > 0 ? (
        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg">
          {recentItems.slice(0, 9).map(item => {
            const iconMap = { resource: IconFileText, exercise: IconBrain, note: IconNotes };
            const Icon = iconMap[item.type] || IconFileText;
            const pathMap = { resource: '/resource/', exercise: '/exercises/', note: '/note/' };
            const labelMap = { resource: 'Resource', exercise: 'Exercise', note: 'Note' };
            return (
              <Card key={`${item.type}-${item.id}`} withBorder radius="md" padding="lg" style={{ cursor: 'pointer' }} onClick={() => navigate(`${pathMap[item.type]}${item.id}`)}>
                <Group mb="xs">
                  <Icon size={18} stroke={1.5} />
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>{labelMap[item.type]}</Text>
                </Group>
                <Text fw={600} c="#171738" lineClamp={2}>{item.title}</Text>
                {item.subject_name && (
                  <Text size="sm" c="dimmed" mt={4}>{item.subject_name}</Text>
                )}
              </Card>
            );
          })}
        </SimpleGrid>
      ) : (
        <Card withBorder radius="md" padding="xl">
          <Center style={{ height: 150 }}>
            <Text c="dimmed">No recent items found.</Text>
          </Center>
        </Card>
      )}

      {/* Create Subject Modal */}
      <Modal opened={subjectModalOpened} onClose={closeSubjectModal} title="Create New Subject" centered>
        <Stack>
          <TextInput required label="Subject Name" placeholder="e.g. Calculus I" data-autofocus />
          <Textarea label="Description (Optional)" placeholder="Brief overview of the subject" rows={3} />
          <ColorInput label="Color Tag" defaultValue="#593C8F" format="hex" swatches={['#25262b', '#868e96', '#fa5252', '#e64980', '#be4bdb', '#7950f2', '#4c6ef5', '#228be6', '#15aabf', '#12b886', '#40c057', '#82c91e', '#fab005', '#fd7e14']} />
          <Group justify="flex-end" mt="md">
            <Button variant="default" onClick={closeSubjectModal}>
              Cancel
            </Button>
            <Button onClick={closeSubjectModal}>Create Subject</Button>
          </Group>
        </Stack>
      </Modal>
    </Box>
  );
}
