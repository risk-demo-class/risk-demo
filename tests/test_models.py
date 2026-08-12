import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models import Course, DeviceBinding, Enrollment, Student


class EducationModelTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_enrollment_links_a_student_to_a_course(self):
        self.session.add_all(
            [
                Student(user_id="STU-001", role="学生", student_id_hash="sid-hash"),
                Course(course_id="CRS-001", name="Python 入门", category="编程", price=299, total_hours=20),
                Enrollment(
                    enrollment_id="ENR-001",
                    user_id="STU-001",
                    course_id="CRS-001",
                    paid_amount=299,
                ),
                DeviceBinding(
                    binding_id="DEV-001",
                    user_id="STU-001",
                    device_fingerprint_hash="device-hash",
                ),
            ]
        )
        self.session.commit()

        enrollment = self.session.get(Enrollment, "ENR-001")
        self.assertEqual(enrollment.user_id, "STU-001")
        self.assertEqual(enrollment.course_id, "CRS-001")
