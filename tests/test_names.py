from datetime import datetime, timedelta, timezone

from homework_helper import names
from homework_helper.canvas import Assignment

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)
_ids = iter(range(1, 1000))


def work(title, days=1, marked_done=False):
    return Assignment(id=next(_ids), course_id=1, course="Physics", title=title,
                      kind="assignment", due=NOW + timedelta(days=days), points=5.0,
                      url="", submitted=False, missing=False, graded=False,
                      marked_done=marked_done)


class MemoryNames:
    def __init__(self, known=None):
        self.known = dict(known or {})

    def load(self):
        return dict(self.known)

    def save(self, new):
        self.known |= new


def test_simple_names():
    assert names.simple_name("Quiz 2: MCQ (Displacement, Velocity, and Acceleration)") == "Quiz 2"
    assert names.simple_name("STEM Fluency Assignment 3") == "STEM Fluency 3"
    assert names.simple_name("Quiz 1 (10/01/26)") == "Quiz 1"
    assert names.simple_name("Formal Lab: Free Fall") == "Formal Lab: Free Fall"


def test_asks_only_about_new_titles_and_keeps_the_answers():
    asked = []

    def namer(titles):
        asked.append(titles)
        return {"Motion Lab Informal Lab write-up": "Motion Lab write-up"}

    kept = MemoryNames({"CH 03 HW": "Chapter 3 homework"})
    hw = names.add_names([work("CH 03 HW"), work("Motion Lab Informal Lab write-up"),
                          work("STEM Fluency Assignment 3")], kept, namer)
    assert asked == [["Motion Lab Informal Lab write-up", "STEM Fluency Assignment 3"]]
    assert [a.name for a in hw] == ["Chapter 3 homework", "Motion Lab write-up",
                                    "STEM Fluency 3"]
    assert kept.known["Motion Lab Informal Lab write-up"] == "Motion Lab write-up"


def test_falls_back_to_rules_when_bedrock_fails():
    def broken(titles):
        raise RuntimeError("throttled")
    [a] = names.add_names([work("Quiz 2: MCQ (Kinematics)")], MemoryNames(), broken)
    assert a.name == "Quiz 2"


def test_names_that_sound_alike_are_not_used():
    kept = MemoryNames({"Chapter 3.1-3.4 pre-lecture": "Chapter 3 pre-lecture",
                        "Chapter 3.5-3.6 pre-lecture": "Chapter 3 pre-lecture"})
    hw = names.add_names([work("Chapter 3.1-3.4 pre-lecture"),
                          work("Chapter 3.5-3.6 pre-lecture")], kept, lambda t: {})
    assert [a.name for a in hw] == ["Chapter 3.1-3.4 pre-lecture", "Chapter 3.5-3.6 pre-lecture"]


def test_file_names_round_trip(tmp_path):
    kept = names.FileNames(str(tmp_path / "names.json"))
    assert kept.load() == {}
    kept.save({"CH 03 HW": "Chapter 3 homework"})
    kept.save({"Quiz 2": "Quiz 2"})
    assert kept.load() == {"CH 03 HW": "Chapter 3 homework", "Quiz 2": "Quiz 2"}


def homework():
    hw = [work("Pre-lab for Acceleration of a Freely Falling Object"),
          work("Formal Lab 1: Free Fall Acceleration Lab Report", days=9),
          work("Motion Lab Informal Lab write-up"),
          work("Quiz 1 (10/01/26)", days=-11, marked_done=True),
          work("Quiz 2: MCQ (Displacement, Velocity, and Acceleration)"),
          work("CH 03 HW"),
          work("STEM Fluency Assignment 3"),
          work("STEM Fluency Assignment 4", days=7)]
    return names.add_names(hw, MemoryNames(), lambda t: {})


def titles(found):
    return [a.title for a in found]


def test_finds_what_the_student_said():
    hw = homework()
    assert titles(names.find(hw, "free fall pre lab")) == [
        "Pre-lab for Acceleration of a Freely Falling Object"]
    assert titles(names.find(hw, "free fall lab report")) == [
        "Formal Lab 1: Free Fall Acceleration Lab Report"]
    assert titles(names.find(hw, "quiz two")) == [
        "Quiz 2: MCQ (Displacement, Velocity, and Acceleration)"]
    assert titles(names.find(hw, "chapter 3 homework")) == ["CH 03 HW"]
    assert titles(names.find(hw, "motion lab write-up")) == ["Motion Lab Informal Lab write-up"]
    hw.append(names.add_names([work("Pre-Lab for Intro to Motion 1-5 labs")], MemoryNames(),
                              lambda t: {})[0])
    assert titles(names.find(hw, "motion lab")) == ["Motion Lab Informal Lab write-up"]
    assert titles(names.find(hw, "STEM Fluency 3")) == ["STEM Fluency Assignment 3"]


def test_unclear_requests_return_every_close_match():
    assert titles(names.find(homework(), "stem fluency")) == [
        "STEM Fluency Assignment 3", "STEM Fluency Assignment 4"]


def test_vague_requests_list_up_to_three():
    hw = homework() + names.add_names([work("Pre-lab for Force lab"), work("Prelab for Inclines")],
                                      MemoryNames(), lambda t: {})
    assert len(names.find(hw, "pre lab")) == 3


def test_finds_nothing_for_unknown_work():
    assert names.find(homework(), "history essay") == []
    assert names.find(homework(), "") == []


def test_undo_only_looks_at_work_marked_done():
    hw = homework()
    assert titles(names.find(hw, "quiz", done=False)) == ["Quiz 1 (10/01/26)"]
    assert titles(names.find(hw, "quiz")) == [
        "Quiz 2: MCQ (Displacement, Velocity, and Acceleration)"]
