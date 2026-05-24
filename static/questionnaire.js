const form = getElement('fitnessForm');
const resultDiv = getElement('result');

const planConfig = {
  lose: {
    title: 'Weight Loss Plan',
    description: 'Focus on full body workouts combined with cardio to maximize calorie burn and fat loss.',
    scheduleFn: generateFullBodyCardioSchedule,
  },
  build: {
    title: 'Muscle Building Plan',
    description: 'Push-Pull-Legs split to target different muscle groups for optimal growth.',
    scheduleFn: generatePushPullLegsSchedule,
  },
  maintain: {
    title: 'Maintenance Plan',
    description: 'Upper-Lower split to maintain your current fitness level and strength.',
    scheduleFn: generateUpperLowerSchedule,
  },
};

form?.addEventListener('submit', function (event) {
  event.preventDefault();

  const gender = getElement('gender')?.value || '';
  const age = parseInt(getElement('age')?.value || '', 10);
  const weight = parseFloat(getElement('weight')?.value || '');
  const height = parseFloat(getElement('height')?.value || '');
  const goal = getElement('goal')?.value || '';
  const level = getElement('level')?.value || '';
  const workoutDays = parseInt(getElement('workoutDays')?.value || '', 10);
  const legDays = parseInt(getElement('legDays')?.value || '', 10);
  const injuries = getElement('injuries')?.value || '';
  const weakMuscles = getElement('weakMuscles')?.value || '';
  const equipment = getElement('equipment')?.value || '';
  const volume = getElement('volume')?.value || '';

  if (!validateInputs(gender, age, weight, height, goal, level, workoutDays, legDays, equipment, volume)) {
    return;
  }

  const userData = { gender, age, weight, height, goal, level, workoutDays, legDays, injuries, weakMuscles, equipment, volume };
  const plan = generatePlan(userData);

  showLoading();

  setTimeout(() => {
    fetch('/api/save-plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userData: userData, plan: plan })
})
.then(r => r.json())
.then(data => {
    displayPlan(plan);
    setTimeout(() => {
        window.location.href = '/dashboard';
    }, 3000);
})
.catch(err => {
    console.error('Error saving plan:', err);
});
  }, 2000);
});

// Validation function
function validateInputs(gender, age, weight, height, goal, level, workoutDays, legDays, equipment, volume) {
    let isValid = true;
    let errors = [];

    if (!gender) {
        errors.push('Please select your gender.');
        isValid = false;
    }

    if (isNaN(age) || age < 10 || age > 100) {
        errors.push('Please enter a valid age between 10-100.');
        isValid = false;
    }

    if (isNaN(weight) || weight < 30 || weight > 300) {
        errors.push('Please enter a valid weight between 30-300 kg.');
        isValid = false;
    }

    if (isNaN(height) || height < 100 || height > 250) {
        errors.push('Please enter a valid height between 100-250 cm.');
        isValid = false;
    }

    if (!goal) {
        errors.push('Please select a goal.');
        isValid = false;
    }

    if (!level) {
        errors.push('Please select your level.');
        isValid = false;
    }

    if (isNaN(workoutDays) || workoutDays < 1 || workoutDays > 7) {
        errors.push('Please enter workout days between 1-7.');
        isValid = false;
    }

    if (isNaN(legDays) || legDays < 0 || legDays > 7) {
        errors.push('Please enter leg days between 0-7.');
        isValid = false;
    }

    if (!equipment) {
        errors.push('Please select your fitness equipment.');
        isValid = false;
    }

    if (!volume) {
        errors.push('Please select your volume preference.');
        isValid = false;
    }

    if (!isValid) {
        alert(errors.join('\n'));
    }

    return isValid;
}

// Generate workout plan based on goal
function generatePlan(data) {
    let plan = {
        title: '',
        description: '',
        schedule: []
    };

    switch (data.goal) {
        case 'lose':
            plan.title = 'Weight Loss Plan';
            plan.description = 'Focus on full body workouts combined with cardio to maximize calorie burn and fat loss.';
            plan.schedule = generateFullBodyCardioSchedule(data.workoutDays);
            break;
        case 'build':
            plan.title = 'Muscle Building Plan';
            plan.description = 'Push-Pull-Legs split to target different muscle groups for optimal growth.';
            plan.schedule = generatePushPullLegsSchedule(data.workoutDays);
            break;
        case 'maintain':
            plan.title = 'Maintenance Plan';
            plan.description = 'Upper-Lower split to maintain your current fitness level and strength.';
            plan.schedule = generateUpperLowerSchedule(data.workoutDays);
            break;
    }

    return plan;
}

// Generate schedule for weight loss
function generateFullBodyCardioSchedule(days) {
    const baseSchedule = [
        'Day 1: Full Body Strength + 30 min Cardio',
        'Day 2: Rest or Light Cardio',
        'Day 3: Full Body Strength + 30 min Cardio',
        'Day 4: Rest or Light Cardio',
        'Day 5: Full Body Strength + 30 min Cardio',
        'Day 6: Active Recovery',
        'Day 7: Rest'
    ];

    return baseSchedule.slice(0, days * 2 - 1); // Adjust based on days
}

// Generate schedule for muscle building
function generatePushPullLegsSchedule(days) {
    const baseSchedule = [
        'Day 1: Push (Chest, Shoulders, Triceps)',
        'Day 2: Pull (Back, Biceps)',
        'Day 3: Legs (Quads, Hamstrings, Calves)',
        'Day 4: Rest',
        'Day 5: Push (Chest, Shoulders, Triceps)',
        'Day 6: Pull (Back, Biceps)',
        'Day 7: Legs (Quads, Hamstrings, Calves)'
    ];

    return baseSchedule.slice(0, days);
}

// Generate schedule for maintenance
function generateUpperLowerSchedule(days) {
    const baseSchedule = [
        'Day 1: Upper Body',
        'Day 2: Lower Body',
        'Day 3: Rest',
        'Day 4: Upper Body',
        'Day 5: Lower Body',
        'Day 6: Active Recovery',
        'Day 7: Rest'
    ];

    return baseSchedule.slice(0, days);
}

// Show loading effect
function showLoading() {
    resultDiv.innerHTML = '<div class="loading">Generating your plan...</div>';
    resultDiv.classList.remove('show');
    setTimeout(() => {
        resultDiv.classList.add('show');
    }, 100);
}

// Display the generated plan
function displayPlan(plan) {
    let html = '<div class="plan">';
    html += `<h3>${plan.title}</h3>`;
    html += `<p>${plan.description}</p>`;
    html += '<h4>Your Weekly Schedule:</h4>';
    html += '<ul>';
    plan.schedule.forEach(day => {
        html += `<li>${day}</li>`;
    });
    html += '</ul>';
    html += '</div>';

    resultDiv.innerHTML = html;
    resultDiv.classList.remove('show');
    setTimeout(() => {
        resultDiv.classList.add('show');
    }, 100);
}